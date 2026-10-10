import { Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from '@/app/Shell'
import { OverviewPage } from '@/features/payroll/OverviewPage'
import { ActionsPage } from '@/features/payroll/ActionsPage'
import { ReviewPage } from '@/features/payroll/ReviewPage'
import { NotificationsPage } from '@/features/payroll/NotificationsPage'
import { PeoplePage } from '@/features/people/PeoplePage'
import { AddEmployeePage } from '@/features/people/AddEmployeePage'
import { EmployeeProfilePage } from '@/features/people/EmployeeProfilePage'
import { EmployeeFormPage } from '@/features/people/EmployeeFormPage'

export function AppRouter() {
  return (
    <Routes>
      <Route path="/form/:token" element={<EmployeeFormPage />} />
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/payroll/overview" replace />} />
        <Route path="/payroll/overview" element={<OverviewPage />} />
        <Route path="/payroll/actions" element={<ActionsPage />} />
        <Route path="/payroll/employees" element={<Navigate to="/people" replace />} />
        <Route path="/payroll/review" element={<ReviewPage />} />
        <Route path="/payroll/notifications" element={<NotificationsPage />} />
        <Route path="/people" element={<PeoplePage />} />
        <Route path="/people/add" element={<AddEmployeePage />} />
        <Route path="/people/:id" element={<EmployeeProfilePage />} />
        <Route path="*" element={<Navigate to="/payroll/overview" replace />} />
      </Route>
    </Routes>
  )
}
