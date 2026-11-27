/** Dictation language: what Whisper listens for. Hindi and Kannada modes expect English drug names and
 *  numbers mixed in, the way 108 crews talk. */
export type AsrLang = 'en' | 'hi' | 'kn' | 'auto'
export const ASR_LANGS: { k: AsrLang; label: string; short: string; hint: string }[] = [
  { k: 'en', label: 'English', short: 'EN', hint: 'English handover' },
  { k: 'hi', label: 'हिंदी + English', short: 'हिं', hint: 'Hindi mixed with English drug names' },
  { k: 'kn', label: 'ಕನ್ನಡ + English', short: 'ಕನ್ನ', hint: 'Kannada mixed with English drug names' },
  { k: 'auto', label: 'Detect', short: 'Auto', hint: 'Let Whisper detect the language' },
]
const KEY = 'fs_asr_lang'
export const asrLang = (): AsrLang => { try { return (localStorage.getItem(KEY) as AsrLang) || 'en' } catch { return 'en' } }
export const setAsrLang = (l: AsrLang) => { try { localStorage.setItem(KEY, l) } catch { /* noop */ } window.dispatchEvent(new Event('fs:asrlang')) }
