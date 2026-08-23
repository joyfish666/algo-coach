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
    retry: '重试',
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
    run: '运行',
    submit: '提交',
    use_local_cases: '使用本地自定义用例',
    custom_cases: '自定义用例',
    custom_cases_hint: '编辑后保存到 testcases.txt，运行时勾选「使用本地自定义用例」生效',
    save_cases: '保存用例',
    cases_saved: '用例已保存',
    verdict_accepted: '通过',
    verdict_wrong_answer: '答案错误',
    verdict_compile_error: '编译错误',
    verdict_runtime_error: '运行时错误',
    verdict_tle: '超出时间限制',
    verdict_mle: '超出内存限制',
    verdict_ole: '输出超限',
    verdict_unknown: '结果未知',
    verdict_unknown_hint: '判定超时但提交已进入站内历史，请在站内确认该提交结果',
    label_runtime: '用时',
    label_memory: '内存',
    label_beat: '击败',
    label_cases_passed: '用例通过',
    label_input: '输入',
    label_expected: '期望输出',
    label_actual: '实际输出',
    label_stdout: '标准输出',
    label_compile_error: '编译错误详情',
    label_runtime_error: '运行时错误详情',
    loading_problem: '正在加载题目…',
    load_failed: '加载失败',
    unsupported_problem: '该题属于非算法类别（如数据库），暂不支持在本地工作台作答',
    premium_problem: '付费题需要会员权限，无法拉取题面',
    restore_draft: '检测到更新的本地草稿',
    restore: '恢复草稿',
    discard_draft: '忽略',
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
    retry: 'Retry',
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
    run: 'Run',
    submit: 'Submit',
    use_local_cases: 'Use local custom testcases',
    custom_cases: 'Custom testcases',
    custom_cases_hint:
      'Edits are saved to testcases.txt; tick "use local custom testcases" to apply them on Run',
    save_cases: 'Save cases',
    cases_saved: 'Cases saved',
    verdict_accepted: 'Accepted',
    verdict_wrong_answer: 'Wrong Answer',
    verdict_compile_error: 'Compile Error',
    verdict_runtime_error: 'Runtime Error',
    verdict_tle: 'Time Limit Exceeded',
    verdict_mle: 'Memory Limit Exceeded',
    verdict_ole: 'Output Limit Exceeded',
    verdict_unknown: 'Result Unknown',
    verdict_unknown_hint:
      'Judging timed out but the submission entered your site history — verify it there',
    label_runtime: 'Runtime',
    label_memory: 'Memory',
    label_beat: 'Beats',
    label_cases_passed: 'Cases passed',
    label_input: 'Input',
    label_expected: 'Expected',
    label_actual: 'Actual',
    label_stdout: 'stdout',
    label_compile_error: 'Compile error details',
    label_runtime_error: 'Runtime error details',
    loading_problem: 'Loading problem…',
    load_failed: 'Failed to load',
    unsupported_problem:
      'This is a non-algorithm category (e.g. database) and is not supported in the local workbench yet',
    premium_problem: 'Premium problem requires a membership; cannot fetch the statement',
    restore_draft: 'Newer local draft detected',
    restore: 'Restore draft',
    discard_draft: 'Discard',
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
