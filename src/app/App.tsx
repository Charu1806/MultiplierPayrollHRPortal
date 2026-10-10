import { BrowserRouter } from 'react-router-dom'
import { AppRouter } from '@/app/router'
import { Bootstrap } from '@/app/Bootstrap'

export function App() {
  return (
    <BrowserRouter>
      <Bootstrap>
        <AppRouter />
      </Bootstrap>
    </BrowserRouter>
  )
}
