import type { SplitSession } from '../types'

export interface SessionRepository {
  loadDraft(): Promise<SplitSession | null>
  saveDraft(session: SplitSession): Promise<void>
  clearDraft(): Promise<void>
  listSessions(): Promise<SplitSession[]>
  saveSession(session: SplitSession): Promise<void>
  deleteSession(id: string): Promise<void>
  generateId(): string
}
