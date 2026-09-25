import '@testing-library/jest-dom/vitest'

// jsdom does not implement the clipboard API; components treat rejection as
// "unavailable" and no-op, so a resolving stub keeps CopyButton tests sane.
if (!navigator.clipboard) {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: async () => {} },
    configurable: true,
  })
}

// jsdom lacks matchMedia; harmless polyfill for future component needs.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })
}
