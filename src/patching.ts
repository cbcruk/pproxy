/**
 * Response transforms — the edits a rule applies to the real server's
 * response instead of replacing it.
 *
 * A rule that sets `body` mocks: the server is never contacted. A rule that
 * sets `merge_patch` or `patches` transforms: the request goes upstream and
 * the response comes back patched. Transforms are the cheaper option when a
 * schema is large and only a field or two has to change.
 *
 * Ported from the Chrome extension sibling project `srikae`, which solved the
 * same problem in the browser first. Nothing here touches HTTP — a transform
 * is a pure function from one JSON value to another, so a rule that patches a
 * response is unit testable without a proxy, exactly like a rule that mocks
 * one.
 */

/**
 * One entry of a rule's `patches` list.
 *
 * Field names carry no case convention, so this is both the rules-file form
 * and the in-memory one.
 */
export interface PathPatchData {
  /** Where to write, in the path DSL — see {@link parsePath}. */
  path: string
  /** The value to write there. */
  value: unknown
}

/** One step of a parsed path: an object key, an array index, or every element. */
export type PathStep =
  | { type: 'key'; key: string }
  | { type: 'index'; index: number }
  | { type: 'wildcard' }

/** A patch whose path has been parsed, so a bad path fails at load rather than mid-request. */
interface CompiledPatch {
  /** The path as written, kept for error messages and `check` output. */
  path: string
  /** The parsed form of {@link path}. */
  steps: PathStep[]
  /** The value to write. */
  value: unknown
}

/** Splits a path segment into its leading key and its trailing bracket groups. */
const SEGMENT_RE = /^([^[\]]*)((?:\[[^\]]*\])*)$/
/** Finds each bracket group inside the trailing part of a segment. */
const BRACKET_RE = /\[[^\]]*\]/g

/**
 * Parse a path into steps.
 *
 * The DSL is deliberately small: dots descend into objects, `[n]` selects one
 * array element, and an empty `[]` selects every element of an array. That
 * empty-bracket wildcard is the whole reason the DSL exists, because a JSON
 * merge patch cannot reach inside an array.
 *
 * ```
 * data.user.name          → key key key
 * data.appointments[].status
 * data.items[0].id
 * ```
 *
 * @param path The path as written in a rule.
 * @returns The steps, in the order they are applied.
 * @throws If a segment is malformed, an index is not a non-negative integer,
 * or the path is empty.
 */
export function parsePath(path: string): PathStep[] {
  const steps: PathStep[] = []

  for (const segment of path.split('.')) {
    const match = SEGMENT_RE.exec(segment)
    if (!match) throw new Error(`invalid path segment: "${segment}"`)

    const [, key = '', brackets = ''] = match
    if (key) steps.push({ type: 'key', key })

    for (const group of brackets.match(BRACKET_RE) ?? []) {
      const inner = group.slice(1, -1).trim()
      if (inner === '') {
        steps.push({ type: 'wildcard' })
        continue
      }
      const index = Number(inner)
      if (!Number.isInteger(index) || index < 0) {
        throw new Error(`invalid array index: "${group}" in path "${path}"`)
      }
      steps.push({ type: 'index', index })
    }
  }

  if (steps.length === 0) throw new Error('path is empty')
  return steps
}

/**
 * Write `value` at every location `steps` selects.
 *
 * Returns a new value rather than mutating, so a rule can be applied to the
 * same document twice and give the same answer.
 *
 * The last step writes, creating the key if the object does not have it. Every
 * step before that only descends: a key on an array, an index past the end, or
 * a missing intermediate key leaves the document unchanged. A patch that
 * silently misses is easier to debug than one that invents the structure it
 * expected to find.
 */
function writePath(node: unknown, steps: PathStep[], value: unknown): unknown {
  const [step, ...rest] = steps
  if (step === undefined) return value

  if (step.type === 'wildcard') {
    if (!Array.isArray(node)) return node
    return node.map((element) => writePath(element, rest, value))
  }

  if (step.type === 'index') {
    if (!Array.isArray(node) || step.index >= node.length) return node
    return node.map((element, index) =>
      index === step.index ? writePath(element, rest, value) : element,
    )
  }

  if (!isPlainObject(node)) return node
  if (!(step.key in node) && rest.length > 0) return node
  return { ...node, [step.key]: writePath(node[step.key], rest, value) }
}

/**
 * Apply a JSON merge patch (RFC 7386) to a document.
 *
 * A patch that is not an object replaces the target outright. Inside an
 * object, `null` deletes a key and everything else merges recursively.
 * Arrays are values, not containers, so a patched array replaces the old one
 * whole — that limit is what {@link parsePath} exists to work around.
 */
export function mergePatch(target: unknown, patch: unknown): unknown {
  if (!isPlainObject(patch)) return patch

  const result: Record<string, unknown> = isPlainObject(target) ? { ...target } : {}
  for (const [key, value] of Object.entries(patch)) {
    if (value === null) delete result[key]
    else result[key] = mergePatch(result[key], value)
  }
  return result
}

/**
 * The transform fields of a rule, as they appear in a rules file.
 *
 * snake_case to match the rules-file format; {@link ResponseTransform} is the
 * in-memory form.
 */
export interface ResponseTransformData {
  /**
   * A JSON merge patch (RFC 7386) applied to the response. An explicit `null`
   * means "no patch" rather than "replace the document with null" — use
   * `body` to replace a response outright.
   */
  merge_patch?: unknown
  /** Path patches applied to the response, in order. */
  patches?: PathPatchData[] | null
}

/**
 * The edit a rule makes to the real server's response.
 *
 * A merge patch runs first, then each path patch in order, so a rule can
 * reshape an object and then rewrite a field inside an array in one pass.
 */
export class ResponseTransform {
  /** The parsed path patches, applied in order after {@link mergePatch}. */
  readonly #patches: readonly CompiledPatch[]

  /**
   * Build a transform.
   *
   * @param mergePatch The merge patch, or `undefined` for none. `null` is a
   * patch that replaces the document, so the two are not interchangeable here.
   * @param patches Path patches, already parsed.
   * @throws If a patch path is malformed.
   */
  constructor(
    readonly mergePatch: unknown = undefined,
    patches: readonly PathPatchData[] = [],
  ) {
    this.#patches = patches.map((patch) => ({
      path: patch.path,
      steps: parsePath(patch.path),
      value: patch.value,
    }))
  }

  /**
   * Create a transform from the transform fields of a rule.
   *
   * @returns The transform, or `null` when the rule sets neither field and so
   * mocks rather than transforms.
   * @throws If `patches` is not a list, an entry has no `path`, or a path is
   * malformed.
   */
  static fromData(data: ResponseTransformData): ResponseTransform | null {
    const merge = data.merge_patch ?? undefined
    const raw = data.patches ?? []
    if (!Array.isArray(raw)) throw new Error(`"patches" must be a list, got ${typeof raw}`)
    for (const patch of raw) {
      if (typeof patch?.path !== 'string') {
        throw new Error(`patch is missing "path": ${JSON.stringify(patch)}`)
      }
    }
    if (merge === undefined && raw.length === 0) return null
    return new ResponseTransform(merge, raw)
  }

  /** The paths this transform writes to, as written in the rule. */
  get paths(): string[] {
    return this.#patches.map((patch) => patch.path)
  }

  /**
   * Apply the transform to a parsed response body.
   *
   * @param body The response as parsed from JSON.
   * @returns A new value; `body` itself is not modified.
   */
  apply(body: unknown): unknown {
    let result = this.mergePatch === undefined ? body : mergePatch(body, this.mergePatch)
    for (const patch of this.#patches) result = writePath(result, patch.steps, patch.value)
    return result
  }

  /** Render the transform as a one-line label for CLI output. */
  describe(): string {
    const parts: string[] = []
    if (this.mergePatch !== undefined) parts.push('merge_patch')
    if (this.#patches.length > 0) parts.push(this.#patches.map((patch) => patch.path).join(', '))
    return `patch(${parts.join(' + ')})`
  }
}

/** Narrow to a non-array object, the only shape merged or descended into by key. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
