import serviceTerms from './TERMS_OF_SERVICE_v1.0.0.md';
import privacyPolicy from './PRIVACY_POLICY_v1.0.0.md';
import generalConsent from './GENERAL_PERSONAL_DATA_CONSENT_v1.0.0.md';
import sensitiveConsent from './SENSITIVE_DATA_CONSENT_v1.0.0.md';

export const POLICY_DOCUMENTS = {
  service_terms: {
    title: '서비스 이용약관',
    filename: 'TERMS_OF_SERVICE_v1.0.0.md',
    markdown: serviceTerms,
  },
  privacy_policy: {
    title: '개인정보처리방침',
    filename: 'PRIVACY_POLICY_v1.0.0.md',
    markdown: privacyPolicy,
  },
  general_personal_data: {
    title: '개인정보 수집 및 이용',
    filename: 'GENERAL_PERSONAL_DATA_CONSENT_v1.0.0.md',
    markdown: generalConsent,
  },
  sensitive_data: {
    title: '민감정보 처리',
    filename: 'SENSITIVE_DATA_CONSENT_v1.0.0.md',
    markdown: sensitiveConsent,
  },
} as const;

export type PolicyDocumentId = keyof typeof POLICY_DOCUMENTS;
