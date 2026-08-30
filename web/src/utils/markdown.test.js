import { describe, expect, it } from 'vitest'

import { makeMarkdown } from './markdown'

describe('makeMarkdown', () => {
  it('renders the statement converter pipe tables as real tables', () => {
    const md = makeMarkdown()
    const html = md.render('| 整数 | 二进制 |\n| --- | --- |\n| 1 | 001 |')
    expect(html).toContain('<table>')
    expect(html).toContain('<th>整数</th>')
    expect(html).toContain('<td>001</td>')
  })

  it('escapes raw html in statement content', () => {
    const html = makeMarkdown().render('<b>x</b>')
    expect(html).not.toContain('<b>')
  })
})
