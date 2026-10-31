import { lazy, type ComponentType } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { LinkButton } from '../components/ui/button'
import { EmptyState, PageSkeleton } from '../components/ui/feedback'
import { ForgotPassword, Login, ResetPassword, Signup, VerifyEmail, Welcome } from '../features/auth/Welcome'
import { AboutStep, FamilyStep, ProcessingStep, StatementStep } from '../features/onboarding/Onboarding'
import { useSaathi } from '../features/saathi/context'
import { useAuth } from '../lib/auth'
import { AppShell } from './AppShell'
import { useEffect } from 'react'

// Route-level code splitting keeps the first load small.
function lz(loader: () => Promise<any>, name: string) {
  return lazy(() => loader().then((m) => ({ default: m[name] as ComponentType<any> })))
}
const CardDetail = lz(() => import('../features/cards/Cards'), 'CardDetail')
const CardOptimizerPage = lz(() => import('../features/cards/Cards'), 'CardOptimizerPage')
const CardsHome = lz(() => import('../features/cards/Cards'), 'CardsHome')
const ExploreCards = lz(() => import('../features/cards/Cards'), 'ExploreCards')
const CardDocumentUpload = lz(() => import('../features/cards/Cards'), 'CardDocumentUpload')
const Dashboard = lz(() => import('../features/dashboard/Dashboard'), 'Dashboard')
const Documents = lz(() => import('../features/documents/Documents'), 'Documents')
const Family = lz(() => import('../features/documents/Documents'), 'Family')
const Settings = lz(() => import('../features/documents/Documents'), 'Settings')
const EmiDetail = lz(() => import('../features/emis/Emis'), 'EmiDetail')
const EmisHome = lz(() => import('../features/emis/Emis'), 'EmisHome')
const ReminderSettings = lz(() => import('../features/emis/Emis'), 'ReminderSettings')
const Consult = lz(() => import('../features/insurance/Insurance'), 'Consult')
const Emergency = lz(() => import('../features/insurance/Insurance'), 'Emergency')
const InsuranceCompare = lz(() => import('../features/insurance/Insurance'), 'InsuranceCompare')
const InsuranceExplore = lz(() => import('../features/insurance/Insurance'), 'InsuranceExplore')
const InsuranceHome = lz(() => import('../features/insurance/Insurance'), 'InsuranceHome')
const PolicySummary = lz(() => import('../features/insurance/Insurance'), 'PolicySummary')
const PolicyUpload = lz(() => import('../features/insurance/Insurance'), 'PolicyUpload')
const LoanAnalyze = lz(() => import('../features/loans/Loans'), 'LoanAnalyze')
const LoanCompare = lz(() => import('../features/loans/Loans'), 'LoanCompare')
const LoanDetail = lz(() => import('../features/loans/Loans'), 'LoanDetail')
const LoanDocument = lz(() => import('../features/loans/Loans'), 'LoanDocument')
const LoanNeed = lz(() => import('../features/loans/Loans'), 'LoanNeed')
const LoanResults = lz(() => import('../features/loans/Loans'), 'LoanResults')
const LoansHome = lz(() => import('../features/loans/Loans'), 'LoansHome')
const Review = lz(() => import('../features/profile/Review'), 'Review')
const Profile = lz(() => import('../features/profile/Profile'), 'Profile')
const ReceiptScan = lz(() => import('../features/receipts/Receipts'), 'ReceiptScan')
const Insights = lz(() => import('../features/insights/Insights'), 'Insights')
const Forecast = lz(() => import('../features/forecast/Forecast'), 'Forecast')
const Goals = lz(() => import('../features/goals/Goals'), 'Goals')
const ReceiptDetail = lz(() => import('../features/receipts/Receipts'), 'ReceiptDetail')


function RequireAuth() {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <div className="mx-auto max-w-3xl p-8"><PageSkeleton /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  if (loc.pathname === '/' && ['about', 'family'].includes(user.onboarding_step)) return <Navigate to={`/onboarding/${user.onboarding_step}`} replace />
  return <Outlet />
}

function OpenSaathi() {
  const { setOpen } = useSaathi()
  useEffect(() => { setOpen(true) }, [setOpen])
  return <Navigate to="/" replace />
}

function NotFound() {
  return <EmptyState title="This page doesn't exist" body="The link may be out of date." action={<LinkButton to="/">Go to dashboard</LinkButton>} />
}


export function AppRoutes() {
  return (
        <Routes>
  <Route path="/welcome" element={<Welcome />} />
  <Route path="/login" element={<Login />} />
  <Route path="/signup" element={<Signup />} />
  <Route path="/forgot-password" element={<ForgotPassword />} />
  <Route path="/reset-password" element={<ResetPassword />} />
  <Route path="/verify-email" element={<VerifyEmail />} />
  <Route element={<RequireAuth />}>
    <Route path="/onboarding/about" element={<AboutStep />} />
    <Route path="/onboarding/family" element={<FamilyStep />} />
    <Route path="/onboarding/statement" element={<StatementStep />} />
    <Route path="/onboarding/processing/:id" element={<ProcessingStep />} />
    <Route element={<AppShell />}>
      <Route index element={<Dashboard />} />
      <Route path="/saathi" element={<OpenSaathi />} />
      <Route path="/profile/review" element={<Review />} />
      <Route path="/profile" element={<Profile />} />
      <Route path="/documents/receipts/new" element={<ReceiptScan />} />
      <Route path="/insights" element={<Insights />} />
      <Route path="/forecast" element={<Forecast />} />
      <Route path="/goals" element={<Goals />} />
      <Route path="/documents/receipts/:id" element={<ReceiptDetail />} />
      <Route path="/loans" element={<LoansHome />} />
      <Route path="/loans/need" element={<LoanNeed />} />
      <Route path="/loans/results" element={<LoanResults />} />
      <Route path="/loans/compare" element={<LoanCompare />} />
      <Route path="/loans/p/:id" element={<LoanDetail />} />
      <Route path="/loans/analyze" element={<LoanAnalyze />} />
      <Route path="/loans/documents/:id" element={<LoanDocument />} />
      <Route path="/cards" element={<CardsHome />} />
      <Route path="/cards/explore" element={<ExploreCards />} />
      <Route path="/cards/upload" element={<CardDocumentUpload />} />
      <Route path="/cards/optimize" element={<CardOptimizerPage />} />
      <Route path="/cards/:id" element={<CardDetail />} />
      <Route path="/emis" element={<EmisHome />} />
      <Route path="/emis/:id" element={<EmiDetail />} />
      <Route path="/settings/reminders" element={<ReminderSettings />} />
      <Route path="/insurance" element={<InsuranceHome />} />
      <Route path="/insurance/upload" element={<PolicyUpload />} />
      <Route path="/insurance/policies/:id" element={<PolicySummary />} />
      <Route path="/insurance/explore" element={<InsuranceExplore />} />
      <Route path="/insurance/compare" element={<InsuranceCompare />} />
      <Route path="/insurance/consult" element={<Consult />} />
      <Route path="/insurance/emergency" element={<Emergency />} />
      <Route path="/documents" element={<Documents />} />
      <Route path="/family" element={<Family />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="*" element={<NotFound />} />
    </Route>
  </Route>
</Routes>
  )
}
