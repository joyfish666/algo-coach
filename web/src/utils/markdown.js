import MarkdownIt from 'markdown-it'

/**
 * One MarkdownIt configuration for the whole app.
 *
 * html:false escapes whatever the source emits (model replies, stored
 * statements, AI reports); linkify:false keeps raw URLs inert. Statement
 * and report prose render with breaks:false (CommonMark paragraph rules);
 * chat bubbles use breaks:true for chat-style line wrapping.
 */
export function makeMarkdown({ breaks = false } = {}) {
  return new MarkdownIt({ html: false, linkify: false, breaks })
}
