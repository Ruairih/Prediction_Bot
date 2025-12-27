import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock ResizeObserver for virtualization
class ResizeObserverMock {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

vi.stubGlobal('ResizeObserver', ResizeObserverMock)

// Mock scrollTo for virtual scroll
Element.prototype.scrollTo = vi.fn()
