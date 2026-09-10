import { describe, expect, it } from 'vitest'

import { ResponseTransform, mergePatch, parsePath } from '../src/patching.js'

describe('mergePatch', () => {
  it('merges nested objects without touching siblings', () => {
    const target = { data: { user: { id: '1', name: 'real' }, other: true } }
    expect(mergePatch(target, { data: { user: { name: 'mock' } } })).toEqual({
      data: { user: { id: '1', name: 'mock' }, other: true },
    })
  })

  it('deletes a key when the patch value is null', () => {
    expect(mergePatch({ a: 1, b: 2 }, { b: null })).toEqual({ a: 1 })
  })

  it('adds keys the target does not have', () => {
    expect(mergePatch({ a: 1 }, { b: { c: 2 } })).toEqual({ a: 1, b: { c: 2 } })
  })

  it('replaces an array whole rather than merging into it', () => {
    expect(mergePatch({ items: [1, 2, 3] }, { items: [9] })).toEqual({ items: [9] })
  })

  it('replaces the target outright when the patch is not an object', () => {
    expect(mergePatch({ a: 1 }, 'gone')).toBe('gone')
    expect(mergePatch({ a: 1 }, null)).toBe(null)
  })

  it('does not modify the target', () => {
    const target = { data: { user: { name: 'real' } } }
    mergePatch(target, { data: { user: { name: 'mock' } } })
    expect(target.data.user.name).toBe('real')
  })
})

describe('parsePath', () => {
  it('parses keys, indexes, and the wildcard', () => {
    expect(parsePath('data.items[].status')).toEqual([
      { type: 'key', key: 'data' },
      { type: 'key', key: 'items' },
      { type: 'wildcard' },
      { type: 'key', key: 'status' },
    ])
    expect(parsePath('items[0]')).toEqual([
      { type: 'key', key: 'items' },
      { type: 'index', index: 0 },
    ])
  })

  it('parses stacked brackets', () => {
    expect(parsePath('grid[0][1]')).toEqual([
      { type: 'key', key: 'grid' },
      { type: 'index', index: 0 },
      { type: 'index', index: 1 },
    ])
  })

  it('rejects an index that is not a non-negative integer', () => {
    expect(() => parsePath('items[-1]')).toThrow(/invalid array index/)
    expect(() => parsePath('items[x]')).toThrow(/invalid array index/)
  })

  it('rejects an empty path', () => {
    expect(() => parsePath('')).toThrow(/empty/)
  })
})

describe('ResponseTransform', () => {
  it('is null when a rule sets neither field', () => {
    expect(ResponseTransform.fromData({})).toBeNull()
    expect(ResponseTransform.fromData({ merge_patch: null, patches: null })).toBeNull()
  })

  it('applies a merge patch', () => {
    const transform = ResponseTransform.fromData({ merge_patch: { data: { ok: false } } })!
    expect(transform.apply({ data: { ok: true, id: 1 } })).toEqual({ data: { ok: false, id: 1 } })
  })

  it('rewrites every element of an array, which a merge patch cannot', () => {
    const transform = ResponseTransform.fromData({
      patches: [{ path: 'data.appointments[].status', value: 'CONFIRMED' }],
    })!
    expect(
      transform.apply({ data: { appointments: [{ id: 1, status: 'PENDING' }, { id: 2 }] } }),
    ).toEqual({
      data: { appointments: [{ id: 1, status: 'CONFIRMED' }, { id: 2, status: 'CONFIRMED' }] },
    })
  })

  it('applies the merge patch before the path patches', () => {
    const transform = ResponseTransform.fromData({
      merge_patch: { items: [{ n: 1 }, { n: 2 }] },
      patches: [{ path: 'items[].n', value: 0 }],
    })!
    expect(transform.apply({ items: [] })).toEqual({ items: [{ n: 0 }, { n: 0 }] })
  })

  it('leaves the document alone when a path does not fit', () => {
    const transform = ResponseTransform.fromData({
      patches: [
        { path: 'data.missing.deep', value: 1 },
        { path: 'data.items[5].id', value: 1 },
        { path: 'data.items[].id', value: 1 },
      ],
    })!
    const body = { data: { items: 'not an array' } }
    expect(transform.apply(body)).toEqual(body)
  })

  it('does not modify the document it is given', () => {
    const transform = ResponseTransform.fromData({ patches: [{ path: 'items[].n', value: 0 }] })!
    const body = { items: [{ n: 1 }] }
    transform.apply(body)
    expect(body).toEqual({ items: [{ n: 1 }] })
  })

  it('rejects a malformed path at load time, not mid-request', () => {
    expect(() => ResponseTransform.fromData({ patches: [{ path: 'a[z]', value: 1 }] })).toThrow(
      /invalid array index/,
    )
  })

  it('rejects a patch with no path', () => {
    expect(() =>
      ResponseTransform.fromData({ patches: [{ value: 1 } as unknown as { path: string; value: unknown }] }),
    ).toThrow(/missing "path"/)
  })

  it('describes what it patches, for check output', () => {
    const transform = ResponseTransform.fromData({
      merge_patch: { a: 1 },
      patches: [{ path: 'b[].c', value: 2 }],
    })!
    expect(transform.describe()).toBe('patch(merge_patch + b[].c)')
    expect(transform.paths).toEqual(['b[].c'])
  })
})
