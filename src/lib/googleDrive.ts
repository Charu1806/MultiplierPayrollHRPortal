/** Google sign-in (Identity Services) then Drive Picker. Scope is drive.file only. */

const SCOPE = 'https://www.googleapis.com/auth/drive.file'
const MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'image/jpeg',
  'image/png',
].join(',')

export type DrivePick = {
  fileId: string
  fileName: string
  accessToken: string
}

export class DrivePickCancelled extends Error {
  constructor() {
    super('Google sign-in cancelled')
    this.name = 'DrivePickCancelled'
  }
}

type TokenResponse = {
  access_token?: string
  error?: string
}

type PickerDoc = { id: string; name: string }

type PickerData = {
  action: string
  docs?: PickerDoc[]
}

type PickerBuilder = {
  setAppId: (id: string) => PickerBuilder
  setOAuthToken: (token: string) => PickerBuilder
  setDeveloperKey: (key: string) => PickerBuilder
  setTitle: (title: string) => PickerBuilder
  setOrigin: (origin: string) => PickerBuilder
  addView: (view: unknown) => PickerBuilder
  setCallback: (cb: (data: PickerData) => void) => PickerBuilder
  build: () => { setVisible: (visible: boolean) => void }
}

type DocsView = {
  setIncludeFolders: (include: boolean) => DocsView
  setSelectFolderEnabled: (enabled: boolean) => DocsView
  setMimeTypes: (types: string) => DocsView
}

declare global {
  interface Window {
    google?: {
      accounts: {
        oauth2: {
          initTokenClient: (config: {
            client_id: string
            scope: string
            callback: (response: TokenResponse) => void
            error_callback?: (error: { type?: string; message?: string }) => void
          }) => { requestAccessToken: (override?: { prompt?: string }) => void }
        }
      }
      picker: {
        Action: { PICKED: string; CANCEL: string }
        DocsView: new () => DocsView
        PickerBuilder: new () => PickerBuilder
      }
    }
    gapi?: { load: (api: string, callback: () => void) => void }
  }
}

function clientId() {
  return import.meta.env.VITE_GOOGLE_CLIENT_ID || ''
}

function apiKey() {
  return import.meta.env.VITE_GOOGLE_API_KEY || ''
}

function appId() {
  return import.meta.env.VITE_GOOGLE_APP_ID || ''
}

export function googleDriveReady() {
  return Boolean(clientId() && apiKey() && appId())
}

function loadScript(id: string, src: string): Promise<void> {
  const existing = document.getElementById(id) as HTMLScriptElement | null
  if (existing?.dataset.loaded === '1') return Promise.resolve()
  return new Promise((resolve, reject) => {
    const script = existing ?? document.createElement('script')
    script.id = id
    script.src = src
    script.async = true
    script.onload = () => {
      script.dataset.loaded = '1'
      resolve()
    }
    script.onerror = () => reject(new Error('Could not load Google sign-in. Check your connection.'))
    if (!existing) document.head.appendChild(script)
  })
}

let ready: Promise<void> | null = null

function ensureGoogle(): Promise<void> {
  if (!googleDriveReady()) {
    return Promise.reject(new Error('Google Drive not set up – see README'))
  }
  if (!ready) {
    ready = (async () => {
      await loadScript('google-gsi', 'https://accounts.google.com/gsi/client')
      await loadScript('google-api', 'https://apis.google.com/js/api.js')
      await new Promise<void>((resolve, reject) => {
        if (!window.gapi) {
          reject(new Error('Could not load Google sign-in. Check your connection.'))
          return
        }
        window.gapi.load('picker', () => resolve())
      })
    })().catch((err) => {
      ready = null
      throw err
    })
  }
  return ready
}

function requestAccessToken(): Promise<string> {
  const google = window.google
  if (!google) return Promise.reject(new Error('Could not load Google sign-in. Check your connection.'))
  return new Promise((resolve, reject) => {
    const client = google.accounts.oauth2.initTokenClient({
      client_id: clientId(),
      scope: SCOPE,
      callback: (response) => {
        if (response.error || !response.access_token) {
          if (response.error === 'access_denied') {
            reject(new DrivePickCancelled())
            return
          }
          reject(new Error('Google sign-in did not finish. Try again.'))
          return
        }
        resolve(response.access_token)
      },
      error_callback: (error) => {
        if (error.type === 'popup_closed' || error.type === 'popup_failed_to_open') {
          reject(
            error.type === 'popup_failed_to_open'
              ? new Error('Allow popups for this site, then click Sign in with Google again.')
              : new DrivePickCancelled(),
          )
          return
        }
        reject(new Error(error.message || 'Google sign-in did not finish. Try again.'))
      },
    })
    // Empty prompt reuses a session when one exists; otherwise Google shows the account window.
    client.requestAccessToken({ prompt: '' })
  })
}

function openPicker(accessToken: string): Promise<DrivePick> {
  const google = window.google
  if (!google) return Promise.reject(new Error('Could not load Google sign-in. Check your connection.'))
  return new Promise((resolve, reject) => {
    const view = new google.picker.DocsView()
      .setIncludeFolders(true)
      .setSelectFolderEnabled(false)
      .setMimeTypes(MIME_TYPES)
    const picker = new google.picker.PickerBuilder()
      .setAppId(appId())
      .setOAuthToken(accessToken)
      .setDeveloperKey(apiKey())
      .setTitle('Choose a file from Drive')
      .setOrigin(window.location.origin)
      .addView(view)
      .setCallback((data) => {
        if (data.action === google.picker.Action.PICKED && data.docs?.[0]) {
          const doc = data.docs[0]
          resolve({ fileId: doc.id, fileName: doc.name, accessToken })
          return
        }
        if (data.action === google.picker.Action.CANCEL) {
          reject(new DrivePickCancelled())
        }
      })
      .build()
    picker.setVisible(true)
  })
}

/** Opens the Google account window, then the Drive file picker. */
export async function pickDriveFile(): Promise<DrivePick> {
  await ensureGoogle()
  const accessToken = await requestAccessToken()
  return openPicker(accessToken)
}
