/** Clarity API DTOs — match server responses (context.md §6, §14). */

export type PrototypeDate = string
export type Country = 'India' | 'UK' | 'Germany' | 'Brazil'

export type CompanyConfig = {
  id?: string
  name: string
  logoInitials: string
  logoBg: string
  logoFg: string
  workspaceSubtitle: string
  hrTool: string
  syncCaption: string
  syncAgoMinutes: number
  payrollCaption: string
  multiplierBrandColor: string
  admin: { name: string; role: string; initials: string; email?: string }
  financeAdmin?: { name: string; role: string; initials: string; email?: string }
  countryAdmins?: {
    code: 'IN' | 'UK' | 'DE' | 'BR'
    country: Country
    name: string
    role: string
    initials: string
    email: string
  }[]
  prototypeBar: string
}
export type Severity = 'blocking' | 'deadline_risk' | 'needs_confirmation' | 'next_cycle'
export type IssueStatus = 'open' | 'resolved'
export type CountryStatus = 'On track' | 'Action needed' | 'Deadline risk'
export type EmployeeStatus = 'Active' | 'Exiting' | 'Exited' | 'Removed'

export type PrototypeDatesResponse = {
  dates: string[]
  labels: string[]
  options?: { value: string; label: string }[]
  default?: string
  min?: string
  max?: string
  keyDates?: { value: string; label: string }[]
}

export type CustomerDto = {
  id: string
  name: string
  hrTool: string
}

export type CycleDto = {
  id: string
  label: string
  stage: string
  inputFinalisation: string
  calculation?: string
  reviewOpen?: string
  reviewClose?: string
  approval: string
  fundingDue: string
  submitted?: string
  payDate: string
  changedLines: number
  matchedLines: number
  needsHumanCheck: number
  approved: boolean
  employeeCount?: number
}

export type CycleCurrentResponse = {
  customer: CustomerDto
  cycle: CycleDto
  asOf: string
  countdown: string
  approvalCountdown?: string
  reviewCountdown?: string
  reviewWindow?: string
  november?: {
    open: boolean
    label: string
    inputFinalisation: string
    approval: string
    payDate: string
  }
  fundingVisible?: boolean
  submittedVisible?: boolean
  inputsOpen?: boolean
  dates?: {
    cutoff?: string
    inputDeadline?: string
    finalSync?: string
    fundingRequest?: string
    calculation?: string
    reviewOpen?: string
    reviewClose?: string
    approval?: string
    fundingDue?: string
    submitted?: string
    payDate?: string
    novCutoff?: string
  }
}

export type CountryRollup = {
  country: Country
  code?: string
  employeeCount: number
  status: CountryStatus
  actionNeededCount?: number
  href?: string | null
}

export type UpNextItem =
  | {
      kind: 'milestone'
      title: string
      deadline: string
      deadlineEnd?: string
      detail: string
      href?: string | null
      viewOnly?: boolean
    }
  | {
      kind: 'issue'
      issueId: string
      title: string
      deadline: string
      country?: string
      severity?: Severity
      who?: string
    }
  | {
      kind: 'reminder'
      title: string
      deadline: string
      owner?: string
    }

export type ChangesReminder = {
  title: string
  body: string
  actions: { label: string; href: string }[]
}

export type OutcomeDto = {
  payDate: string
  total: number
  inRun?: number
  paidOnTime: { count: number; href: string }
  movedToNovember: { count: number; employees: { id: string; name: string; reason?: string | null }[] }
  stillAtRisk: { count: number; employees: { id: string; name: string }[]; message: string }
  paymentReturned?: {
    count: number
    employees: { id: string; name: string; reason?: string | null }[]
    href?: string
    message?: string | null
  }
}

export type OverviewResponse = CycleCurrentResponse & {
  statusLine: {
    openActions: number
    countdown: string
    signedOff?: boolean
    actionsHref?: string
    reviewHref?: string
    kind?: string
    message?: string
    href?: string
  }
  reviewMeta?: {
    window?: string
    needsCheck?: number
    remaining?: number
    closedWithoutSignOff?: boolean
    unappliedCount?: number
    calculationDate?: string
    reviewOpen?: string
    reviewClose?: string
    cycleKey?: string
  }
  countries: CountryRollup[]
  upNext: UpNextItem[]
  changesReminder?: ChangesReminder | null
  outcome?: OutcomeDto | null
  funding?: { receivedOn: string; countries: { country: string; received: boolean; label: string }[] } | null
  fundsAddedOn?: string | null
  submitted?: { message: string } | null
  notInRun?: { count: number; employees: { id: string; name: string; country?: string }[]; message: string; href: string }
  carryOvers?: { id: string; name: string; reason?: string | null }[]
  sync?: {
    lastSync: {
      syncedAt: string
      trigger: string
      actor: string
      summary?: string | null
      userInitiated?: boolean
      added?: number
      changed?: number
      exited?: number
    } | null
    manualRemaining: number
    maxPerDay: number
  } | null
  readiness?: {
    changed: number
    needAction: number
    needApproval: number
    matched: number
    reconciles: boolean
    openIssues: number
  } | null
  changeBreakdown?: {
    added: number
    exited: number
    bonus: number
    hike: number
    leave: number
    other: number
  } | null
  recentChanges?: { employeeId?: string | null; kind: string; summary: string; cycleAssignment: string; at: string }[]
  fundingEstimate?: {
    currency: string
    required: number
    available: number
    toTransfer: number
    illustrative: boolean
    note?: string
  } | null
  fundingVariance?: {
    forex: number
    employerRates: number
    other: number
    total: number
    reconciles: boolean
    currency: string
  } | null
  payOutcomes?: {
    simulated: boolean
    paidSuccessfully: { count: number; of: number }
    paidPreviousSalary: {
      count: number
      employees: { id?: string; name: string; reason: string }[]
      href?: string | null
    }
    missingInputs: {
      count: number
      employees: { id?: string; name: string; field?: string; owner?: string; issueId?: string }[]
      href?: string | null
    }
    addedAfterCutoff: { count: number; employees: { name: string; prorated: number }[] }
    paymentReturned: { count: number }
    byCountry?: Record<string, CountryPaySlice>
  } | null
  octoberSummary?: {
    tone: string
    message: string
    href?: string
    linkLabel?: string
    month?: string
    payDateLabel?: string
    paid?: number
    of?: number
    paidPreviousSalary?: { count: number; href?: string | null }
    missingInputs?: { count: number; href?: string | null }
    addedAfterCutoff?: { count: number; href?: string | null }
    paymentReturned?: { count: number; href?: string | null }
    added?: { count: number; href?: string | null }
    left?: { count: number; href?: string | null }
    byCountry?: Record<string, CountryPaySlice>
  } | null
  previousPayrolls?: {
    tone: string
    message: string
    month?: string
    payDateLabel?: string
    paid?: number
    of?: number
    paidPreviousSalary?: { count: number; href?: string | null }
    missingInputs?: { count: number; href?: string | null }
    addedAfterCutoff?: { count: number; href?: string | null }
    paymentReturned?: { count: number; href?: string | null }
    added?: { count: number; href?: string | null }
    left?: { count: number; href?: string | null }
    byCountry?: Record<string, CountryPaySlice>
  }[]
}

export type CountryPaySlice = {
  paid: number
  of: number
  paidPreviousSalary: { count: number; href?: string | null }
  missingInputs: { count: number; href?: string | null }
  addedAfterCutoff: { count: number; href?: string | null }
  paymentReturned: { count: number; href?: string | null }
  added?: { count: number; href?: string | null }
  left?: { count: number; href?: string | null }
}

export type IssueDto = {
  id: string
  title: string
  severity: Severity
  kind?: string
  employeeId: string | null
  employeeName?: string | null
  country: Country
  owner: string
  deadline: string
  source: string
  impact: string
  detail: string | null
  status: IssueStatus
  resolvedAt: string | null
  resolvedBy: string | null
  resolutionLog: string | null
  reminderSentOn?: string | null
  reminderSentAt?: string | null
  reminderLabel?: string | null
  carriedOver?: boolean
  employeeOwnedFields?: string[]
  hrOwnedFields?: string[]
  missingFields?: string[]
  demoValues?: Record<string, string>
  aiNote?: string | null
  facts?: { submitted?: string; payHistory?: string; openSalaryHref?: string }
}

export type IssuesListResponse = {
  issues: IssueDto[]
  asOf: string
}

export type ResolveIssueBody = {
  resolution: string
  payload?: Record<string, unknown>
  actor?: string
  asOf?: string
}

export type ResolveIssueResponse = {
  issue: IssueDto
  overview: OverviewResponse
  canApprove?: boolean
  partial?: boolean
}

export type PayTimingDto = {
  level: 'green' | 'amber' | 'red'
  message: string
  run?: string
  reason?: string | null
  showOffCycleStub: boolean
  instantPaymentDisabled?: boolean
}

export type OneOffDto = {
  label: string
  amount: number
  cycleMonth?: string | null
  type?: string
  recordedOn?: string
}

export type SalaryDto = {
  base: number
  allowances: number
  unpaidLeaveDays: number
  deductions: number
  oneTimePayments: OneOffDto[]
  oneTimeTotal: number
  gross: number
  taxRate: number
  tax: number
  net: number
  cycle: string
}

export type MappingRowDto = {
  sourceSystem: string | null
  sourceField: string | null
  multiplierField: string
  value: string
  status: string
  confidence: string | null
}

export type JourneyStepDto = {
  key: string
  label: string
  at: string
}

export type EmployeeDto = {
  id: string
  name: string
  role: string
  country: Country
  currency: string
  septemberPay?: number
  monthlyNet: number
  salary?: SalaryDto
  dateAdded: string | null
  isNew: boolean
  status?: EmployeeStatus
  stage: string
  source: string
  workEmail: string | null
  hireDate: string | null
  managerName: string | null
  missingFields: string[]
  /** Missing fields the model says are required to pay. Manager is not included. */
  paymentMissingFields?: string[]
  fieldValues?: Record<string, string>
  hrRecord?: {
    basePay?: number
    identity: { field: string; state: 'value' | 'missing' | 'on_file'; value?: string | null; owner?: string }
    aadhaar: { field: string; state: 'value' | 'missing' | 'on_file' | 'not_recorded' | 'not_used'; value?: string | null }
    bank: { field: string; state: 'value' | 'missing' | 'on_file'; value?: string | null; owner?: string }
    insurance: 'added' | 'not_added'
    employeeAdds: { field: string; owner: string }[]
    other: string
  }
  oneOffs: OneOffDto[]
  /** LLM explanation when a first month is prorated. Amounts come from the pay engine. */
  payExplanation?: string | null
  /** Pay cut explained by the same review line (why flagged, source, LLM warning). */
  payAdjustment?: {
    label: string
    amount: number
    changeSummary?: string
    whyFlagged?: string
    matchingSource?: string
    llmDecision?: LlmDecisionDto | null
  } | null
  savedIn?: string
  saveMessage?: string
  payrollSnapshot?: {
    baseSalary: number
    allowances: number
    unpaidLeaveDays: number
    lastSyncAt?: string | null
    readOnly: boolean
  }
  changedThisCycle?: boolean
  matchedSource?: string | null
  editedByYou?: boolean
  actionNeeded: boolean
  payTiming: PayTimingDto
  ifNoActionWillBePaid: string | null
  payOutlook?: {
    amount: number
    currency: string
    month: string
    status: string
    note: string
    display: string
    tone: string
    banner?: { text: string; tone: string }
  }
  exit?: Record<string, unknown> | null
  notes: string | null
  featured: boolean
  demoValues?: Record<string, string>
  journeySteps?: JourneyStepDto[] | null
  mappings?: MappingRowDto[]
  /** Stored letters. A view link is shown only when that letter exists. */
  letters?: {
    offer?: { id: string; fileName: string; kind: string } | null
    bonus?: { id: string; fileName: string; kind: string } | null
    hike?: { id: string; fileName: string; kind: string } | null
  } | null
}

export type EmployeesListResponse = {
  total?: number
  page?: number
  pageSize?: number
  employees: EmployeeDto[]
  removed?: EmployeeDto[]
  count: number
  asOf: string
}

export type CreateEmployeeBody = {
  name?: string
  legalName?: string
  country?: string
  workLocation?: string
  role?: string
  jobTitle?: string
  workEmail?: string
  email?: string
  hireDate?: string
  manager?: string
  managerName?: string
  monthlyNet?: number
  baseSalary?: number
  asOf?: string
}

export type AttachDocumentBody = {
  fixture?: string
  filename?: string
  fileName?: string
  asOf?: string
}

export type MissingFieldsBody = {
  asOf?: string
  fillSample?: boolean
  fields?: Record<string, string>
  source?: string
  [key: string]: unknown
}

export type LlmDecisionDto = {
  recommend: 'approve' | 'hold'
  confidence: number
  reason: string
  label?: string
  source?: 'llm' | 'fallback' | 'unavailable' | 'error' | 'approved'
}

export type ReviewLineDto = {
  id: string
  employeeId: string | null
  employeeName: string
  country: string
  changeSummary: string
  whyFlagged: string
  matchingSource: string
  origin?: string
  needsHumanCheck: boolean
  approved?: boolean
  rejected?: boolean
  approvedOn?: string | null
  approvedBy?: string | null
  openHref?: string
  requiresEmployeeNotified?: boolean
  llmDecision?: LlmDecisionDto | null
  /** What happens to this line if it is still unapproved when the review closes. */
  carryNote?: string | null
}

export type ReviewResponse = {
  available: boolean
  windowState?: 'before' | 'open' | 'closed'
  readOnly?: boolean
  cycleKey?: string
  message?: string
  header?: string
  closedMessage?: string | null
  inputsNote?: string | null
  changedLines: number
  matchedLines: number
  needsHumanCheck: number
  numbersLabel?: string | null
  showOpenExtras?: boolean
  lines: ReviewLineDto[]
  remaining?: number
  badgeCount?: number
  canSignOff?: boolean
  signOffHint?: string | null
  signedOff?: boolean
  closedWithoutSignOff?: boolean
  nextReviewLabel?: string
  nextReviewOpen?: string
  nextReviewClose?: string
  unappliedChanges?: {
    id?: string | null
    name: string
    href?: string
    septemberPay?: string | null
    note?: string
    banner?: string
    kind?: string
  }[]
  closedSummary?: {
    tone: string
    message: string
    nextHref?: string
    nextLinkLabel?: string
    employees?: {
      id?: string | null
      name: string
      href?: string
      note?: string
      banner?: string
      kind?: string
    }[]
  } | null
  signoff?: {
    signedOn: string
    signedAt: string
    signedBy: string
    reopened?: boolean
    reopenedNote?: string | null
  } | null
  notInRun?: { count: number; employees: { id: string; name: string; country?: string }[]; message: string; href: string } | null
  inputsOpen?: boolean
  canApprove?: boolean
  approved: boolean
  asOf?: string
  ifUnapproved?: {
    headline: string
    nextCycle?: string
    settled?: boolean
    items: {
      employeeId: string
      name: string
      kind: string
      kindLabel: string
      previousPay: string
      difference: string
      nextCycle?: string
      note: string
    }[]
  } | null
}

export type ApproveResponse = {
  approved?: boolean
  signedOff?: boolean
  message: string
  summary?: { inThisRun: string; movingToNovember: string[] }
  review?: ReviewResponse
}

export type NotificationListItem = {
  id: string
  sendDate: string
  createdAt?: string | null
  unread?: boolean
  recipient: string
  channel: string
  subject: string
  bodySummary: string | null
  actionCount: number | null
  kind?: string
  delivery?: 'sent' | 'not_sent_smtp_missing' | null
  ctaLabel?: string
  audience?: 'global' | 'country' | 'employee' | 'finance' | null
  country?: string | null
  cc?: string | null
}

export type NotificationsListResponse = {
  notifications: NotificationListItem[]
  asOf: string
}

export type NotificationActionDto = {
  actionText: string
  deadline: string | null
  issueId: string | null
  href?: string | null
}

export type NotificationPolicyLink = {
  label: string
  href: string
  note?: string | null
}

export type FundingConfirm = {
  decision: 'yes' | 'no' | null
  decidedOn: string | null
  fundsAddedOn: string | null
  cycleKey: string
}

export type NotificationDetail = NotificationListItem & {
  actions: NotificationActionDto[]
  policy?: NotificationPolicyLink | null
  fundingConfirm?: FundingConfirm | null
  cta: {
    label: string
    href: string
  }
}

export type DocumentFixtureDto = {
  id: string
  filename: string
  docType: string
  targetName: string
  country: string | null
  allFieldsOk: boolean
  notes: string | null
}

export type DocumentFixturesResponse = {
  fixtures: DocumentFixtureDto[]
}

export type AiCheckDto = {
  label: string
  message: string
  direction: string
  ratio: number
  multiple: string
}

export type ExtractResult = {
  fileName: string
  usedFallback: boolean
  fallbackNote: string | null
  mappings: MappingRowDto[]
  journeySteps: JourneyStepDto[]
  employee?: EmployeeDto
}
