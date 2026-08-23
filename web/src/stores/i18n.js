import { defineStore } from 'pinia'

const STORAGE_KEY = 'algocoach-lang'

export const MESSAGES = {
  zh: {
    nav_problems: '题库',
    nav_daily: '每日一题',
    nav_analyze: '分析',
    nav_settings: '设置',
    coming_soon: '该功能正在开发中，敬请期待',
    goto_problems: '返回题库',
    setup_title: '引导配置',
    setup_subtitle: '首次使用需完成初始化配置',
    setup_body:
      '图形化配置向导将于后续版本提供。当前可先通过 API 写入 Cookie，完成后刷新本页即可开始使用。',
    problems_title: '题库',
    problems_subtitle: '全量题目缓存与筛选',
    problems_sync: '同步题库',
    daily_title: '每日一题',
    daily_subtitle: '保持手感，一天一道',
    analyze_title: '分析',
    analyze_subtitle: '解题统计与薄弱点',
    settings_title: '设置',
    settings_subtitle: '偏好与账号',
    settings_appearance: '外观',
    settings_interface_lang: '界面语言',
    settings_coding_lang: '默认刷题语言',
    settings_account: '账号（Cookie）',
    cookie_configured: '已配置',
    cookie_missing: '未配置',
    save: '保存',
    saved_ok: '已保存',
    stat_total: '总解题数',
    stat_easy: 'Easy 通过',
    stat_medium: 'Medium 通过',
    stat_hard: 'Hard 通过',
    chart_tags: '标签掌握度',
    problem_statement: '题面',
    problem_editor: '编辑器',
    theme_light: '浅色',
    theme_dark: '暗色',
    theme_system: '跟随系统',
  },
  en: {
    nav_problems: 'Problems',
    nav_daily: 'Daily',
    nav_analyze: 'Analytics',
    nav_settings: 'Settings',
    coming_soon: 'This feature is under development — stay tuned',
    goto_problems: 'Back to problems',
    setup_title: 'Setup',
    setup_subtitle: 'Finish first-run configuration to continue',
    setup_body:
      'The guided wizard arrives in a later release. Meanwhile you can configure your cookie through the API, then reload this page.',
    problems_title: 'Problems',
    problems_subtitle: 'Full problem cache with filtering',
    problems_sync: 'Sync problems',
    daily_title: 'Daily Problem',
    daily_subtitle: 'One problem a day keeps rust away',
    analyze_title: 'Analytics',
    analyze_subtitle: 'Your progress at a glance',
    settings_title: 'Settings',
    settings_subtitle: 'Preferences & account',
    settings_appearance: 'Appearance',
    settings_interface_lang: 'Interface language',
    settings_coding_lang: 'Default coding language',
    settings_account: 'Account (Cookie)',
    cookie_configured: 'Configured',
    cookie_missing: 'Not configured',
    save: 'Save',
    saved_ok: 'Saved',
    stat_total: 'Solved',
    stat_easy: 'Easy solved',
    stat_medium: 'Medium solved',
    stat_hard: 'Hard solved',
    chart_tags: 'Tag mastery',
    problem_statement: 'Statement',
    problem_editor: 'Editor',
    theme_light: 'Light',
    theme_dark: 'Dark',
    theme_system: 'System',
  },
}

function readStoredLang() {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function detectLocale() {
  const lang = (navigator.language || 'en').toLowerCase()
  return lang.startsWith('zh') ? 'zh' : 'en'
}

export const useI18nStore = defineStore('i18n', {
  state: () => ({
    lang: readStoredLang() || detectLocale(),
  }),
  getters: {
    messages(state) {
      return MESSAGES[state.lang] || MESSAGES.en
    },
  },
  actions: {
    t(key, params) {
      let text = this.messages[key] ?? MESSAGES.en[key] ?? key
      if (params) {
        text = text.replace(/\{(\w+)\}/g, (match, name) =>
          params[name] !== undefined ? String(params[name]) : match
        )
      }
      return text
    },
    set(lang) {
      if (!MESSAGES[lang]) return
      this.lang = lang
      try {
        localStorage.setItem(STORAGE_KEY, lang)
      } catch {
      }
    },
  },
})
