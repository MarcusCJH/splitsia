import type { SessionRepository } from '@splitleh/core'
import {
  saveDraft,
  loadDraft,
  clearDraft,
  loadSessions,
  saveSession,
  deleteSession,
  generateId,
} from '../utils/storage'

export const localStorageSessionRepository: SessionRepository = {
  loadDraft: async () => loadDraft(),
  saveDraft: async (session) => { saveDraft(session) },
  clearDraft: async () => { clearDraft() },
  listSessions: async () => loadSessions(),
  saveSession: async (session) => { saveSession(session) },
  deleteSession: async (id) => { deleteSession(id) },
  generateId,
}
