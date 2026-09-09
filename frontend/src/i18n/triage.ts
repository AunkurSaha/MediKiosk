// Multi-lingual copy for staff triage dashboard and patient-facing emergency banner

export interface TriageCopy {
  // Patient emergency notice (calm, non-diagnostic - docs/design.md Section 8)
  patientAlertTitle: string;
  patientAlertMessage: string;
  patientAlertStaffNotified: string;

  // Staff triage dashboard
  dashboardTitle: string;
  dashboardSubtitle: string;
  allAlerts: string;
  filterEmergency: string;
  filterUrgent: string;
  filterAll: string;
  filterNew: string;
  filterAcknowledged: string;
  filterResolved: string;

  // Stats
  statEmergency: string;
  statUrgent: string;
  statAcknowledged: string;
  statTotal: string;

  // Alert Card / Table
  token: string;
  patient: string;
  complaint: string;
  priority: string;
  category: string;
  reason: string;
  triggeringFacts: string;
  status: string;
  detectedAt: string;
  acknowledgedBy: string;
  acknowledgedAt: string;
  actionAcknowledge: string;
  acknowledging: string;
  staffNamePlaceholder: string;
  notePlaceholder: string;
  confirmAcknowledge: string;
  cancel: string;
  noAlerts: string;
  liveFeedConnected: string;
  liveFeedConnecting: string;
}

const en: TriageCopy = {
  patientAlertTitle: 'Staff Assessment Recommended',
  patientAlertMessage:
    'Potential emergency symptoms were detected. Medical staff should assess you promptly.',
  patientAlertStaffNotified: 'Medical staff have been notified.',

  dashboardTitle: 'Staff Triage & Safety Dashboard',
  dashboardSubtitle: 'Deterministic red-flag safety screening & clinical queue escalation',
  allAlerts: 'All Alerts',
  filterEmergency: 'Emergency',
  filterUrgent: 'Urgent',
  filterAll: 'All Priorities',
  filterNew: 'New',
  filterAcknowledged: 'Acknowledged',
  filterResolved: 'Resolved',

  statEmergency: 'Emergency Alerts',
  statUrgent: 'Urgent Alerts',
  statAcknowledged: 'Acknowledged',
  statTotal: 'Total Active',

  token: 'Token',
  patient: 'Patient',
  complaint: 'Complaint',
  priority: 'Priority',
  category: 'Category',
  reason: 'Trigger Reason',
  triggeringFacts: 'Triggering Evidence',
  status: 'Status',
  detectedAt: 'Detected',
  acknowledgedBy: 'Acknowledged By',
  acknowledgedAt: 'Acknowledged At',
  actionAcknowledge: 'Acknowledge Alert',
  acknowledging: 'Saving...',
  staffNamePlaceholder: 'Staff member name / ID (e.g. Nurse Ratched)',
  notePlaceholder: 'Action taken note (e.g. Patient moved to bay 2)',
  confirmAcknowledge: 'Confirm Acknowledgement',
  cancel: 'Cancel',
  noAlerts: 'No alerts matching the selected filter.',
  liveFeedConnected: 'Live Triage Feed Connected',
  liveFeedConnecting: 'Connecting to Triage Feed...',
};

const bn: TriageCopy = {
  patientAlertTitle: 'স্বাস্থ্যকর্মীদের দ্বারা মূল্যায়ন জরুরি',
  patientAlertMessage:
    'জরুরি উপসর্গ সনাক্ত করা হয়েছে। অবিলম্বে স্বাস্থ্যকর্মীদের আপনাকে দেখা প্রয়োজন।',
  patientAlertStaffNotified: 'স্বাস্থ্যকর্মীদের অবহিত করা হয়েছে।',

  dashboardTitle: 'স্টাফ ট্রায়াজ ও সুরক্ষা ড্যাশবোর্ড',
  dashboardSubtitle: 'জরুরি বিপদচিহ্ন স্ক্রীনিং ও স্বাস্থ্যকর্মী অগ্রাধিকার পর্যবেক্ষণ',
  allAlerts: 'সকল সতর্কতা',
  filterEmergency: 'জরুরি (Emergency)',
  filterUrgent: 'জরুরি অগ্রাধিকার (Urgent)',
  filterAll: 'সকল অগ্রাধিকার',
  filterNew: 'নতুন',
  filterAcknowledged: 'স্বীকৃত',
  filterResolved: 'মীমাংসিত',

  statEmergency: 'জরুরি সতর্কতা',
  statUrgent: 'অগ্রাধিকার সতর্কতা',
  statAcknowledged: 'স্বীকৃত',
  statTotal: 'মোট সক্রিয়',

  token: 'টোকেন',
  patient: 'রোগী',
  complaint: 'সমস্যা',
  priority: 'অগ্রাধিকার',
  category: 'বিভাগ',
  reason: 'সতর্কতার কারণ',
  triggeringFacts: 'উৎস প্রমাণ',
  status: 'অবস্থা',
  detectedAt: 'সনাক্তের সময়',
  acknowledgedBy: 'স্বীকৃতকারী',
  acknowledgedAt: 'স্বীকৃতির সময়',
  actionAcknowledge: 'সতর্কতা স্বীকার করুন',
  acknowledging: 'সংরক্ষণ হচ্ছে...',
  staffNamePlaceholder: 'কর্মীর নাম বা আইডি (যেমন: নার্স রুমানা)',
  notePlaceholder: 'গৃহীত ব্যবস্থা সংক্রান্ত নোট (যেমন: রোগীকে পর্যবেক্ষণ কক্ষে নেওয়া হয়েছে)',
  confirmAcknowledge: 'স্বীকৃতি নিশ্চিত করুন',
  cancel: 'বাতিল',
  noAlerts: 'নির্বাচিত ফিল্টারে কোনো সতর্কতা পাওয়া যায়নি।',
  liveFeedConnected: 'সরাসরি ট্রায়াজ ফিড যুক্ত',
  liveFeedConnecting: 'ট্রায়াজ ফিড যুক্ত হচ্ছে...',
};

const hi: TriageCopy = {
  patientAlertTitle: 'स्वास्थ्य कर्मियों द्वारा जांच की सलाह',
  patientAlertMessage:
    'संभावित आपातकालीन लक्षण पाए गए हैं। तुरंत स्वास्थ्य कर्मियों द्वारा आपकी जांच आवश्यक है।',
  patientAlertStaffNotified: 'स्वास्थ्य कर्मियों को सूचित कर दिया गया है।',

  dashboardTitle: 'स्टाफ ट्राइएज एवं सुरक्षा डैशबोर्ड',
  dashboardSubtitle: 'आपातकालीन रेड-फ्लैग स्क्रीनिंग एवं प्राथमिक क्लिनिकल प्राथमिकता',
  allAlerts: 'सभी चेतावनियाँ',
  filterEmergency: 'आपातकालीन (Emergency)',
  filterUrgent: 'अति आवश्यक (Urgent)',
  filterAll: 'सभी प्राथमिकताएँ',
  filterNew: 'नई',
  filterAcknowledged: 'स्वीकृत',
  filterResolved: 'समाधानित',

  statEmergency: 'आपातकालीन चेतावनियाँ',
  statUrgent: 'अति आवश्यक चेतावनियाँ',
  statAcknowledged: 'स्वीकृत',
  statTotal: 'कुल सक्रिय',

  token: 'टोकन',
  patient: 'मरीज़',
  complaint: 'समस्या',
  priority: 'प्राथमिकता',
  category: 'श्रेणी',
  reason: 'चेतावनी का कारण',
  triggeringFacts: 'प्रमाण तथ्य',
  status: 'स्थिति',
  detectedAt: 'पहचाना गया',
  acknowledgedBy: 'स्वीकृतकर्ता',
  acknowledgedAt: 'स्वीकृति का समय',
  actionAcknowledge: 'चेतावनी स्वीकार करें',
  acknowledging: 'सहेजा जा रहा है...',
  staffNamePlaceholder: 'स्टाफ का नाम / आईडी (उदा. नर्स अनीता)',
  notePlaceholder: 'कार्रवाई विवरण (उदा. मरीज़ को इमरजेंसी वार्ड 2 में ले जाया गया)',
  confirmAcknowledge: 'स्वीकृति की पुष्टि करें',
  cancel: 'रद्द करें',
  noAlerts: 'चयनित फ़िल्टर में कोई चेतावनी नहीं है।',
  liveFeedConnected: 'लाइव ट्राइएज फ़ीड कनेक्टेड',
  liveFeedConnecting: 'ट्राइएज फ़ीड से कनेक्ट हो रहा है...',
};

export const triageTranslations = { en, bn, hi };

export function getTriageCopy(lang: string): TriageCopy {
  if (lang === 'bn') return bn;
  if (lang === 'hi') return hi;
  return en;
}
