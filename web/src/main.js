import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import './styles/tokens.css'

const app = createApp(App)
// component-tree errors funnel into console.error so the debug buffer (and
// the user-facing "copy logs" flow) sees render failures that window.onerror
// alone would only partially capture
app.config.errorHandler = (err, _instance, info) => {
  console.error(`[vue:${info}]`, err)
}
app.use(createPinia())
app.use(router)
app.mount('#app')
