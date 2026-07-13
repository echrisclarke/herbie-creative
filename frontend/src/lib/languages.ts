/** Languages shown in Review. Values are stored in brief.localize_to for the AI. */

export type LanguageOption = {
  value: string
  label: string
  /** Older BCP-47 codes that map to this language when loading briefs */
  aliases?: string[]
}

export const LANGUAGE_OPTIONS: LanguageOption[] = [
  { value: 'English', label: 'English', aliases: ['en', 'en-US', 'en-GB', 'en-AU', 'en-CA'] },
  {
    value: 'Chinese (Mandarin)',
    label: 'Chinese (Mandarin)',
    aliases: ['zh', 'zh-CN', 'zh-Hans', 'zh-SG'],
  },
  {
    value: 'Chinese (Cantonese)',
    label: 'Chinese (Cantonese)',
    aliases: ['zh-HK', 'zh-TW', 'yue', 'zh-Hant'],
  },
  { value: 'Spanish', label: 'Spanish', aliases: ['es', 'es-ES', 'es-MX', 'es-US', 'es-AR'] },
  { value: 'Catalan', label: 'Catalan', aliases: ['ca', 'ca-ES'] },
  { value: 'French', label: 'French', aliases: ['fr', 'fr-FR', 'fr-CA', 'fr-BE'] },
  { value: 'German', label: 'German', aliases: ['de', 'de-DE', 'de-AT', 'de-CH'] },
  { value: 'Portuguese (Brazil)', label: 'Portuguese (Brazil)', aliases: ['pt-BR'] },
  {
    value: 'Portuguese (Portugal)',
    label: 'Portuguese (Portugal)',
    aliases: ['pt', 'pt-PT'],
  },
  { value: 'Italian', label: 'Italian', aliases: ['it', 'it-IT'] },
  { value: 'Japanese', label: 'Japanese', aliases: ['ja', 'ja-JP'] },
  { value: 'Korean', label: 'Korean', aliases: ['ko', 'ko-KR'] },
  { value: 'Hindi', label: 'Hindi', aliases: ['hi', 'hi-IN'] },
  { value: 'Bengali', label: 'Bengali', aliases: ['bn', 'bn-IN', 'bn-BD'] },
  { value: 'Tamil', label: 'Tamil', aliases: ['ta', 'ta-IN', 'ta-LK'] },
  { value: 'Telugu', label: 'Telugu', aliases: ['te', 'te-IN'] },
  { value: 'Marathi', label: 'Marathi', aliases: ['mr', 'mr-IN'] },
  { value: 'Gujarati', label: 'Gujarati', aliases: ['gu', 'gu-IN'] },
  { value: 'Kannada', label: 'Kannada', aliases: ['kn', 'kn-IN'] },
  { value: 'Malayalam', label: 'Malayalam', aliases: ['ml', 'ml-IN'] },
  { value: 'Punjabi', label: 'Punjabi', aliases: ['pa', 'pa-IN'] },
  { value: 'Urdu', label: 'Urdu', aliases: ['ur', 'ur-IN', 'ur-PK'] },
  { value: 'Arabic', label: 'Arabic', aliases: ['ar', 'ar-SA', 'ar-EG', 'ar-AE'] },
  { value: 'Hebrew', label: 'Hebrew', aliases: ['he', 'he-IL', 'iw'] },
  { value: 'Russian', label: 'Russian', aliases: ['ru', 'ru-RU'] },
  { value: 'Ukrainian', label: 'Ukrainian', aliases: ['uk', 'uk-UA'] },
  { value: 'Polish', label: 'Polish', aliases: ['pl', 'pl-PL'] },
  { value: 'Dutch', label: 'Dutch', aliases: ['nl', 'nl-NL', 'nl-BE'] },
  { value: 'Swedish', label: 'Swedish', aliases: ['sv', 'sv-SE'] },
  { value: 'Norwegian', label: 'Norwegian', aliases: ['no', 'nb', 'nn', 'nb-NO'] },
  { value: 'Danish', label: 'Danish', aliases: ['da', 'da-DK'] },
  { value: 'Finnish', label: 'Finnish', aliases: ['fi', 'fi-FI'] },
  { value: 'Turkish', label: 'Turkish', aliases: ['tr', 'tr-TR'] },
  { value: 'Greek', label: 'Greek', aliases: ['el', 'el-GR'] },
  { value: 'Thai', label: 'Thai', aliases: ['th', 'th-TH'] },
  { value: 'Vietnamese', label: 'Vietnamese', aliases: ['vi', 'vi-VN'] },
  { value: 'Indonesian', label: 'Indonesian', aliases: ['id', 'id-ID'] },
  { value: 'Malay', label: 'Malay', aliases: ['ms', 'ms-MY'] },
  { value: 'Filipino', label: 'Filipino', aliases: ['fil', 'tl', 'tl-PH'] },
  { value: 'Swahili', label: 'Swahili', aliases: ['sw', 'sw-KE', 'sw-TZ'] },
  { value: 'Klingon', label: 'Klingon', aliases: ['tlh'] },
  { value: 'Elvish (Quenya)', label: 'Elvish (Quenya)', aliases: ['qya'] },
  { value: 'Elvish (Sindarin)', label: 'Elvish (Sindarin)', aliases: ['sjn'] },
]

export const OTHER_LANGUAGE_VALUE = '__other__'

export function normalizeLanguageId(raw: string): string {
  const trimmed = (raw || '').trim()
  if (!trimmed) return 'English'
  const lower = trimmed.toLowerCase()
  for (const opt of LANGUAGE_OPTIONS) {
    if (opt.value.toLowerCase() === lower) return opt.value
    if ((opt.aliases || []).some((a) => a.toLowerCase() === lower)) return opt.value
  }
  return trimmed
}

export function languageLabel(raw: string): string {
  const id = normalizeLanguageId(raw)
  const found = LANGUAGE_OPTIONS.find((o) => o.value === id)
  return found?.label || id
}

export function isEnglishLanguage(raw: string): boolean {
  const id = normalizeLanguageId(raw).toLowerCase()
  return id === 'english' || id.startsWith('english ')
}
