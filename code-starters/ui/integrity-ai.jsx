import { useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";
import {
  AlertTriangle, Shield, Search, Bell, Bot, X, Send,
  DollarSign, CheckCircle, LayoutDashboard, User,
  Briefcase, Filter, Building, Zap, ArrowUp, FileText,
  TrendingUp, Share2, Download, ChevronDown,
  BookOpen, GitBranch, Scale, Landmark, Link2,
  ChevronRight, TriangleAlert, Lightbulb, ClipboardList,
  BarChart2, Globe, AlertCircle, ArrowRight, ThumbsUp, ThumbsDown,
  Clock, CheckSquare, XCircle, PlayCircle, PauseCircle
} from "lucide-react";

// ── DESIGN TOKENS ─────────────────────────────────────────────────────────────
const C = {
  bg:      '#05080f',
  s1:      '#080d1a',
  s2:      '#0c1222',
  s3:      '#101828',
  b0:      '#182033',
  b1:      '#1e2c44',
  b2:      '#253450',
  cyan:    '#00d4ff',
  amber:   '#f59e0b',
  red:     '#ff4040',
  green:   '#00e676',
  purple:  '#a855f7',
  text:    '#e2eaf6',
  dim:     '#8899bb',
  muted:   '#3d5070',
};

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Oxanium:wght@400;500;600;700;800&family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'IBM Plex Sans',sans-serif;background:${C.bg}}
  ::-webkit-scrollbar{width:4px;height:4px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:${C.b1};border-radius:4px}
  input::placeholder{color:${C.muted}}
  input{outline:none}
  button{font-family:inherit;transition:all 0.15s}
  @keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
  @keyframes slideRight{from{opacity:0;transform:translateX(24px)}to{opacity:1;transform:translateX(0)}}
  @keyframes pulseRing{0%,100%{box-shadow:0 0 0 0 rgba(0,212,255,0.4)}50%{box-shadow:0 0 0 6px rgba(0,212,255,0)}}
  @keyframes pkgPulse{0%,100%{opacity:1}50%{opacity:0.55}}
  .fu{animation:fadeUp 0.35s ease both}
  .sr{animation:slideRight 0.4s cubic-bezier(.16,1,.3,1) both}
  .pkg-pulse{animation:pkgPulse 2.5s ease-in-out infinite}
`;

// ── MOCK DATA ─────────────────────────────────────────────────────────────────
const programs = {
  medicare: {
    label: 'Medicare FFS', color: C.cyan,
    kpis: { flagged:'3,241', savings:'$52.7M', resolved:'1,847', confidence:'88%' },
    trend: [
      {m:'Sep',a:180,s:3.2},{m:'Oct',a:214,s:3.8},{m:'Nov',a:198,s:3.5},{m:'Dec',a:245,s:4.1},
      {m:'Jan',a:289,s:5.2},{m:'Feb',a:318,s:5.8},{m:'Mar',a:302,s:5.6},{m:'Apr',a:347,s:6.3},
      {m:'May',a:381,s:7.1},{m:'Jun',a:419,s:7.9},{m:'Jul',a:398,s:7.3},{m:'Aug',a:451,s:8.5},
    ],
    cats: [{n:'Billing Pattern',v:21.3,c:1204},{n:'Network Anomaly',v:16.1,c:847},{n:'Trend Shift',v:9.8,c:623},{n:'Beneficiary Abuse',v:5.5,c:567}],
  },
  medicaid: {
    label: 'Medicaid Dental/Vision', color: C.purple,
    kpis: { flagged:'1,847', savings:'$28.6M', resolved:'1,042', confidence:'84%' },
    trend: [
      {m:'Sep',a:110,s:1.8},{m:'Oct',a:138,s:2.2},{m:'Nov',a:152,s:2.5},{m:'Dec',a:171,s:2.9},
      {m:'Jan',a:195,s:3.3},{m:'Feb',a:218,s:3.7},{m:'Mar',a:234,s:4.0},{m:'Apr',a:256,s:4.4},
      {m:'May',a:278,s:4.8},{m:'Jun',a:295,s:5.1},{m:'Jul',a:312,s:5.4},{m:'Aug',a:338,s:5.9},
    ],
    cats: [{n:'Dental Upcoding',v:11.2,c:634},{n:'Clinic Ring / Shared Attr',v:7.8,c:412},{n:'Unbundling / Repeats',v:5.4,c:387},{n:'Ineligible Provider',v:4.2,c:414}],
  },
};

const feed = [
  {id:1,name:'Advanced Pain Specialists',npi:'1234567890',type:'Billing + Trend',risk:94,conf:89,amt:'$2.1M',flag:'UPCODING · HCPCS CONSOLIDATION',days:2,city:'Miami, FL',spec:'Pain Management',status:'Active'},
  {id:2,name:'Sunrise Medical Group',npi:'9876543210',type:'Network',risk:91,conf:86,amt:'$1.8M',flag:'REFERRAL RING DETECTED',days:3,city:'Houston, TX',spec:'Primary Care',status:'Active'},
  {id:3,name:'Dr. James Kellerman',npi:'1122334455',type:'Billing',risk:89,conf:92,amt:'$847K',flag:'E&M UPCODING · TOP 2% PEERS',days:1,city:'Chicago, IL',spec:'Internal Medicine',status:'Active'},
  {id:4,name:'Gulf Coast DME Supply',npi:'5544332211',type:'Billing',risk:87,conf:84,amt:'$1.2M',flag:'PHANTOM BILLING INDICATORS',days:5,city:'New Orleans, LA',spec:'DME Supplier',status:'Active'},
  {id:5,name:'Premier Diagnostics LLC',npi:'6677889900',type:'Network + Billing',risk:83,conf:81,amt:'$980K',flag:'SELF-REFERRAL · OVER-ORDERING',days:4,city:'Phoenix, AZ',spec:'Diagnostics',status:'Active'},
  {id:6,name:'Dr. Maria Santos',npi:'0099887766',type:'Trend',risk:79,conf:78,amt:'$634K',flag:'SPECIALTY SHIFT ANOMALY',days:7,city:'Los Angeles, CA',spec:'Family Medicine',status:'Cleared'},
  {id:7,name:'Coastal Rehab Center',npi:'1357924680',type:'Network',risk:74,conf:76,amt:'$1.4M',flag:'KICKBACK INDICATORS',days:6,city:'Tampa, FL',spec:'Rehabilitation',status:'Active'},
  {id:8,name:'Dr. Robert Chen',npi:'2468013579',type:'Billing',risk:71,conf:83,amt:'$512K',flag:'MODIFIER ABUSE · 59 MODIFIER',days:8,city:'Seattle, WA',spec:'Surgery',status:'Active'},
];

const hcpcs = [
  {m:"Mar'23",codes:47,top3:38,bill:42,atRisk:4,owner:'old'},{m:"Apr'23",codes:46,top3:39,bill:44,atRisk:5,owner:'old'},
  {m:"May'23",codes:44,top3:40,bill:46,atRisk:5,owner:'old'},{m:"Jun'23",codes:45,top3:41,bill:48,atRisk:6,owner:'old'},
  {m:"Jul'23",codes:41,top3:45,bill:52,atRisk:26,owner:'new'},{m:"Aug'23",codes:35,top3:52,bill:64,atRisk:52,owner:'new'},
  {m:"Sep'23",codes:28,top3:61,bill:82,atRisk:75,owner:'new'},{m:"Oct'23",codes:22,top3:69,bill:98,atRisk:97,owner:'new'},
  {m:"Nov'23",codes:17,top3:77,bill:118,atRisk:117,owner:'new'},{m:"Dec'23",codes:13,top3:84,bill:135,atRisk:134,owner:'new'},
  {m:"Jan'24",codes:10,top3:89,bill:156,atRisk:155,owner:'new'},{m:"Feb'24",codes:8,top3:93,bill:172,atRisk:171,owner:'new'},
  {m:"Mar'24",codes:7,top3:95,bill:187,atRisk:186,owner:'new'},{m:"Apr'24",codes:6,top3:97,bill:199,atRisk:198,owner:'new'},
  {m:"May'24",codes:6,top3:97,bill:208,atRisk:207,owner:'new'},{m:"Jun'24",codes:6,top3:98,bill:216,atRisk:215,owner:'new'},
  {m:"Jul'24",codes:6,top3:98,bill:220,atRisk:219,owner:'new'},{m:"Aug'24",codes:6,top3:98,bill:228,atRisk:227,owner:'new'},
];

const peers = [
  {m:'99215 Rate',pv:78,p90:45,p50:18},{m:'99214 Rate',pv:14,p90:35,p50:38},
  {m:'99213 Rate',pv:5,p90:12,p50:28},{m:'New Pt %',pv:52,p90:28,p50:18},
  {m:'Avg Units',pv:38,p90:21,p50:14},
];

// E&M upcoding data
const emDist = [
  { code:'99211', prov:1,  p90:3,  med:7  },
  { code:'99212', prov:2,  p90:8,  med:18 },
  { code:'99213', prov:5,  p90:22, med:32 },
  { code:'99214', prov:14, p90:42, med:25 },
  { code:'99215', prov:78, p90:25, med:18 },
];
const emTrend = [
  {m:"Mar'23",prov:19,peer:19,owner:'old'},{m:"Apr'23",prov:20,peer:19,owner:'old'},{m:"May'23",prov:18,peer:18,owner:'old'},
  {m:"Jun'23",prov:21,peer:19,owner:'old'},{m:"Jul'23",prov:25,peer:20,owner:'new'},{m:"Aug'23",prov:34,peer:19,owner:'new'},
  {m:"Sep'23",prov:44,peer:18,owner:'new'},{m:"Oct'23",prov:53,peer:19,owner:'new'},{m:"Nov'23",prov:60,peer:20,owner:'new'},
  {m:"Dec'23",prov:66,peer:19,owner:'new'},{m:"Jan'24",prov:70,peer:18,owner:'new'},{m:"Feb'24",prov:73,peer:19,owner:'new'},
  {m:"Mar'24",prov:75,peer:18,owner:'new'},{m:"Apr'24",prov:76,peer:19,owner:'new'},{m:"May'24",prov:77,peer:19,owner:'new'},
  {m:"Jun'24",prov:77,peer:18,owner:'new'},{m:"Jul'24",prov:78,peer:19,owner:'new'},{m:"Aug'24",prov:78,peer:18,owner:'new'},
];

// Network co-billing data
const netNodes = [
  { id:'aps',    label:'Advanced Pain\nSpecialists', x:210, y:135, r:40, color:'#ff4040', risk:94, status:'SUBJECT' },
  { id:'sun',    label:'Sunrise Medical\nGroup',     x:345, y:55,  r:24, color:'#ff4040', risk:91, status:'FLAGGED' },
  { id:'prem',   label:'Premier\nDiagnostics',       x:360, y:200, r:20, color:'#f59e0b', risk:83, status:'FLAGGED' },
  { id:'coast',  label:'Coastal\nRehab Center',      x:75,  y:200, r:18, color:'#f59e0b', risk:74, status:'FLAGGED' },
  { id:'kell',   label:'Dr. James\nKellerman',       x:68,  y:65,  r:22, color:'#ff4040', risk:89, status:'FLAGGED' },
];
const netEdges = [
  { from:'aps', to:'sun',   overlap:34, vol:287, w:3.8 },
  { from:'aps', to:'prem',  overlap:21, vol:178, w:2.5 },
  { from:'aps', to:'coast', overlap:18, vol:152, w:2.1 },
  { from:'aps', to:'kell',  overlap:12, vol:101, w:1.6 },
  { from:'sun', to:'kell',  overlap:9,  vol:76,  w:1.2 },
];
const netTable = [
  { name:'Sunrise Medical Group',  npi:'9876543210', spec:'Primary Care',    overlap:34, vol:287, risk:91, status:'FLAGGED' },
  { name:'Premier Diagnostics LLC',npi:'6677889900', spec:'Diagnostics',     overlap:21, vol:178, risk:83, status:'FLAGGED' },
  { name:'Coastal Rehab Center',   npi:'1357924680', spec:'Rehabilitation',  overlap:18, vol:152, risk:74, status:'FLAGGED' },
  { name:'Dr. James Kellerman',    npi:'1122334455', spec:'Internal Medicine',overlap:12, vol:101, risk:89, status:'FLAGGED' },
];

const evLog = [
  {date:'Jul 15, 2023',type:'Ownership Change',icon:'building',text:'Provider ownership transferred to Pain Management Holdings LLC. CMS-855 enrollment updated. New management structure effective immediately.',sev:'info'},
  {date:'Aug 12, 2023',type:'Pattern Alert',icon:'alert',text:'Automated monitoring detected 18% month-over-month drop in HCPCS code diversity (45 → 37 codes) — first significant deviation from 16-month baseline.',sev:'med'},
  {date:'Aug 28, 2024',type:'AI Detection',icon:'bot',text:'Automated model flagged HCPCS consolidation pattern — 47 → 6 unique codes over 18 months with 98% billing concentration. Pattern change initiated immediately post-ownership transfer.',sev:'high'},
  {date:'Aug 29, 2024',type:'Peer Analysis',icon:'chart',text:'99215 utilization at 78% vs. peer median 18%. Provider ranks in top 1.3% nationally. Rate was normal (19-21%) pre-ownership change, then spiked 311% over 12 months.',sev:'high'},
  {date:'Sep 2, 2024',type:'Network Scan',icon:'network',text:'Co-billing relationship identified with Sunrise Medical Group (NPI: 9876543210). Shared patient overlap: 34%.',sev:'med'},
  {date:'Sep 3, 2024',type:'Claims Pull',icon:'file',text:'847 claims reviewed for FY2024. Estimated overbilling vs. peer-adjusted expected: $2.1M.',sev:'high'},
  {date:'Sep 4, 2024',type:'Analyst Review',icon:'user',text:'Assigned to Analyst J. Morrison. Priority: HIGH. Recommended for site visit, records request, and ownership structure review.',sev:'info'},
];

// ── POLICY KNOWLEDGE GRAPH DATA ───────────────────────────────────────────────
const pkgSignals = [
  {
    id: 'sig1',
    signal: 'HCPCS Code Consolidation',
    icon: TrendingUp, color: C.red,
    anomalyScore: 0.94,
    policies: [
      {
        id: 'P1',
        source: 'CMS IOM Pub. 100-04, Ch. 12 §30.6.1',
        title: 'E&M Documentation Requirements — Level of Service Selection',
        relevance: 97,
        snippet: 'The selection of the appropriate level of E&M service must be based on the key components of the face-to-face encounter and must be supported by documentation in the medical record. Routine assignment of the highest-level code without supporting documentation constitutes improper coding.',
        ruleType: 'Coding Requirement',
      },
      {
        id: 'P2',
        source: 'CMS NCCI Policy Manual, Ch. 1 §D',
        title: 'Medically Unlikely Edits — Units of Service',
        relevance: 88,
        snippet: 'Services billed at frequencies that exceed clinical plausibility for a given patient population or provider specialty are subject to MUE adjudication. Patterns of billing at maximum allowable units across a high proportion of claims indicate systematic abuse rather than legitimate clinical variation.',
        ruleType: 'Billing Integrity',
      },
      {
        id: 'P3',
        source: 'OIG Work Plan FY2024 — Pain Management Focus Area',
        title: 'High-Utilization Pain Management Providers',
        relevance: 82,
        snippet: 'Pain management providers billing a narrow range of high-reimbursement procedure codes at rates substantially above peer cohorts have been identified as a priority review area. Such patterns are consistent with systematic upcoding and code consolidation schemes.',
        ruleType: 'OIG Priority',
      },
    ],
    determination: 'LIKELY VIOLATION',
    determinationConf: 91,
    reasoning: 'The 45-to-6 code reduction occurred within 12 months of ownership transfer (July 15, 2023), during which provider exhibited stable baseline behavior (44-47 codes, 38-41% concentration). This temporal correlation directly contradicts clinical evolution and instead suggests systematic operational changes under new management. The 98% billing concentration in high-reimbursement codes contradicts CMS IOM §30.6.1. OIG FY2024 Work Plan explicitly identifies post-acquisition billing pattern shifts as a priority enforcement area.',
    actions: [
      { type: 'IMMEDIATE', label: 'Prepayment Edit', desc: 'Place provider on prepayment review for codes 99215 and 64483 pending investigation.', priority: 'high' },
      { type: 'INVESTIGATION', label: 'Records Request', desc: 'Issue ADR for 50 randomly sampled 99215 claims to validate medical necessity documentation.', priority: 'high' },
      { type: 'COMPLIANCE', label: 'Provider Education Letter', desc: 'Issue CMS-compliant notice citing IOM §30.6.1 and documentation requirements.', priority: 'med' },
    ],
    policyGap: 'IOM §30.6.1 lacks a quantitative threshold for code concentration ratios, creating enforcement ambiguity for pattern-based upcoding schemes.',
  },
  {
    id: 'sig2',
    signal: 'E&M Level Upcoding',
    icon: AlertTriangle, color: C.amber,
    anomalyScore: 0.89,
    policies: [
      {
        id: 'P4',
        source: 'CMS MLN Matters SE1436',
        title: 'Evaluation and Management Services — Correct Coding',
        relevance: 95,
        snippet: 'Medical complexity and time are the two pathways for code level selection under 2021 E&M guidelines. Providers billing predominantly at 99215 must document either medical decision-making of high complexity or total time exceeding 54 minutes per encounter.',
        ruleType: 'Coding Guidance',
      },
      {
        id: 'P5',
        source: 'CMS Program Integrity Manual, Ch. 3 §3.4',
        title: 'Statistical Aberrant Billing — Provider Outlier Criteria',
        relevance: 90,
        snippet: 'A provider billing at rates exceeding 3 standard deviations above the peer cohort mean for a given service code is classified as a statistical outlier and subject to focused medical review. The threshold for mandatory review is triggered at the 99th percentile for any single E&M code.',
        ruleType: 'Program Integrity',
      },
      {
        id: 'P6',
        source: 'AMA CPT Guidelines 2024 — E&M Complexity Criteria',
        title: 'High-Complexity Medical Decision Making',
        relevance: 79,
        snippet: 'High complexity MDM requires: (1) multiple chronic conditions with severe exacerbation, OR (2) a new condition with uncertain prognosis, AND involves extensive data review and/or high-risk management options. Routine pain management follow-up visits rarely qualify without detailed supporting documentation.',
        ruleType: 'Coding Standard',
      },
    ],
    determination: 'LIKELY VIOLATION',
    determinationConf: 86,
    reasoning: '78% utilization of 99215 vs. 18% peer median places this provider at the 98.7th percentile — well above CMS PIM §3.4 mandatory review threshold (99th percentile ≈ 45%). MLN SE1436 requires documented high-complexity MDM or 54+ minute encounters. For a pain management volume practice billing 847 claims/year, systematic documentation of high complexity MDM at this rate is clinically implausible.',
    actions: [
      { type: 'IMMEDIATE', label: 'Statistical Outlier Flag', desc: 'Formally classify as statistical outlier per PIM §3.4. Triggers mandatory Focused Medical Review.', priority: 'high' },
      { type: 'INVESTIGATION', label: 'Chart Audit — 99215 Claims', desc: 'Targeted audit of 99215 claims: verify MDM documentation meets 2021 E&M high-complexity criteria or ≥54 min documented.', priority: 'high' },
      { type: 'COMPLIANCE', label: 'Overpayment Demand Letter', desc: 'If audit confirms systematic upcoding, issue demand for repayment of difference between 99215 and supported code level (est. $1.1M).', priority: 'med' },
    ],
    policyGap: 'CMS PIM §3.4 outlier trigger is set at the 99th percentile — providers at the 95th–99th percentile (like this case at 98.7th) fall in a governance gap with no mandatory review trigger, only discretionary.',
  },
  {
    id: 'sig3',
    signal: 'Network Co-billing',
    icon: Share2, color: C.amber,
    anomalyScore: 0.83,
    policies: [
      {
        id: 'P7',
        source: 'Social Security Act §1128B(b)',
        title: 'Anti-Kickback Statute — Referral Arrangements',
        relevance: 88,
        snippet: 'Knowingly and willfully offering, paying, soliciting, or receiving remuneration to induce or reward referrals of items or services covered by federal healthcare programs is prohibited. Coordinated referral arrangements that disproportionately direct patients within a closed network may constitute remuneration under this statute.',
        ruleType: 'Federal Statute',
      },
      {
        id: 'P8',
        source: 'CMS Medicare Benefit Policy Manual, Ch. 15 §50',
        title: 'Self-Referral Restrictions — Stark Law Compliance',
        relevance: 81,
        snippet: 'Physicians may not refer Medicare patients to entities with which they have a financial relationship unless a statutory exception applies. Co-ownership arrangements, revenue-sharing agreements, or systematic cross-referrals among providers under shared management warrant Stark Law review.',
        ruleType: 'Regulatory',
      },
    ],
    determination: 'POSSIBLE VIOLATION — FURTHER REVIEW REQUIRED',
    determinationConf: 68,
    reasoning: '34% patient overlap with a co-flagged provider and 4.2× expected referral density are consistent with a coordinated referral arrangement potentially implicating AKS §1128B(b). However, policy grounding is less definitive here — legitimate care coordination, shared EHR systems, or geographic concentration could explain overlap. Determination confidence is lower (68%) pending financial relationship review.',
    actions: [
      { type: 'INVESTIGATION', label: 'Financial Relationship Review', desc: 'Subpoena or request disclosure of any financial relationships, co-ownership, or management agreements between the 4 flagged providers.', priority: 'high' },
      { type: 'INVESTIGATION', label: 'DOJ / OIG Referral Review', desc: 'If financial relationships confirmed, evaluate threshold for DOJ referral under AKS. Engage OIG liaison.', priority: 'med' },
      { type: 'COMPLIANCE', label: 'Network Monitoring', desc: 'Place all 4 co-billed providers on enhanced monitoring. Flag any new shared-patient patterns.', priority: 'med' },
    ],
    policyGap: 'CMS lacks a defined quantitative threshold for referral overlap rates that constitutes a Stark/AKS red flag — investigators must rely on judgment calls, creating inconsistent enforcement across regions.',
  },
];

// Policy Intelligence data (for CMS leadership screen)
const policyGaps = [
  {
    id: 'G1', severity: 'CRITICAL', title: 'No Quantitative Code Concentration Threshold',
    scope: 'E&M & Procedure Coding', affectedProviders: 847, estimatedExposure: '$124M',
    source: 'IOM Pub. 100-04, Ch. 12 §30.6.1',
    description: 'Policy requires E&M codes to reflect documented complexity but provides no numeric threshold for code concentration ratios. Allows systematic cherry-picking schemes to proceed until manually detected.',
    recommendation: 'Establish a maximum 85% billing concentration rule for any 3-code combination within a specialty, triggering automated prepayment review.',
    programImpact: 'medicare',
    casesExposing: 14,
  },
  {
    id: 'G2', severity: 'HIGH', title: 'Outlier Trigger Set Too High (99th Pct)',
    scope: 'Statistical Aberrant Billing',  affectedProviders: 1204, estimatedExposure: '$89M',
    source: 'CMS PIM Ch. 3 §3.4',
    description: 'Mandatory Focused Medical Review is only triggered at the 99th percentile. Providers at 95th–99th percentile — a large cohort — fall in a governance gap with no mandatory review, only discretionary.',
    recommendation: 'Lower mandatory review threshold to 95th percentile for E&M codes. Add a secondary trigger at 90th percentile for providers with ≥3 concurrent anomaly signals.',
    programImpact: 'both',
    casesExposing: 31,
  },
  {
    id: 'G3', severity: 'HIGH', title: 'No Referral Overlap Rate Threshold for AKS Review',
    scope: 'Anti-Kickback / Network Integrity',  affectedProviders: 423, estimatedExposure: '$67M',
    source: 'SSA §1128B(b) / Stark Law',
    description: 'Anti-Kickback and Stark Law provide no quantitative referral overlap threshold. Investigators rely on judgment, creating inconsistent enforcement across MACs and regions.',
    recommendation: 'Define a >25% shared-patient overlap rate between two providers as a rebuttable presumption requiring disclosure of financial relationships.',
    programImpact: 'both',
    casesExposing: 8,
  },
  {
    id: 'G4', severity: 'MEDIUM', title: 'Medicaid HCPCS Edit Lag vs. Medicare',
    scope: 'Claims Processing — NCCI Edits',  affectedProviders: 612, estimatedExposure: '$43M',
    source: 'CMS NCCI Policy Manual / State Medicaid Guidance',
    description: 'Medicaid NCCI edit tables are updated quarterly vs. Medicare\'s monthly cadence, creating a 60–90 day window where new abusive coding patterns can propagate in Medicaid before edits catch up.',
    recommendation: 'Align Medicaid NCCI edit update frequency with Medicare. Implement a rapid-response edit pathway for patterns identified in Medicare fraud cases.',
    programImpact: 'medicaid',
    casesExposing: 19,
  },
];

const policyTrends = [
  {m:'Q1\'23',gaps:8,cases:34,exposure:41},{m:'Q2\'23',gaps:9,cases:41,exposure:49},
  {m:'Q3\'23',gaps:9,cases:38,exposure:46},{m:'Q4\'23',gaps:11,cases:52,exposure:61},
  {m:'Q1\'24',gaps:12,cases:67,exposure:78},{m:'Q2\'24',gaps:13,cases:74,exposure:89},
  {m:'Q3\'24',gaps:13,cases:81,exposure:97},{m:'Q4\'24',gaps:14,cases:91,exposure:114},
];

const cases = [
  {id:'MC-2024-0891',prov:'Advanced Pain Specialists',npi:'1234567890',type:'Billing + Trend',risk:94,status:'Under Review',analyst:'J. Morrison',amt:'$2.1M',date:'Sep 4'},
  {id:'MC-2024-0887',prov:'Sunrise Medical Group',npi:'9876543210',type:'Network',risk:91,status:'Escalated',analyst:'T. Williams',amt:'$1.8M',date:'Sep 2'},
  {id:'MC-2024-0872',prov:'Dr. James Kellerman',npi:'1122334455',type:'Billing',risk:89,status:'Pending',analyst:'Unassigned',amt:'$847K',date:'Sep 1'},
  {id:'MC-2024-0854',prov:'Gulf Coast DME Supply',npi:'5544332211',type:'Billing',risk:87,status:'Under Review',analyst:'M. Johnson',amt:'$1.2M',date:'Aug 28'},
  {id:'MC-2024-0831',prov:'Premier Diagnostics LLC',npi:'6677889900',type:'Network + Billing',risk:83,status:'Closed · Confirmed',analyst:'J. Morrison',amt:'$980K',date:'Aug 15'},
  {id:'MC-2024-0819',prov:'Dr. Maria Santos',npi:'0099887766',type:'Trend',risk:79,status:'Closed · Cleared',analyst:'R. Davis',amt:'—',date:'Aug 10'},
  {id:'MC-2024-0802',prov:'Coastal Rehab Center',npi:'1357924680',type:'Network',risk:74,status:'Pending',analyst:'Unassigned',amt:'$1.4M',date:'Aug 22'},
  {id:'MC-2024-0791',prov:'Dr. Robert Chen',npi:'2468013579',type:'Billing',risk:71,status:'Under Review',analyst:'T. Williams',amt:'$380K',date:'Aug 20'},
];

const canned = {
  codes: "The top 6 HCPCS codes driving 98% of billing are:\n\n• 99215 — Complex office visit (61% of claims)\n• 99214 — Moderate office visit (14%)\n• 64483 — Lumbar nerve block (11%)\n• 62323 — Epidural injection (7%)\n• 72148 — Lumbar MRI (4%)\n• 20610 — Joint injection (3%)\n\nNormal pain management practices bill 30–50+ unique codes. This consolidation to 6 codes is a strong indicator of systematic cherry-picking.",
  compare: "Compared to 847 similar pain management providers in Florida:\n\n• 99215 rate: 78% vs. peer median 21%\n• New patient ratio: 52% vs. 19% median\n• Avg units/claim: 3.8 vs. 1.6 median\n• Monthly billing growth: +442% over 18 months vs. +12% peer average\n\nThis provider ranks in the top 1.3% nationally on 99215 utilization.",
  next: "Recommended investigative steps:\n\n1. Records Request — Pull 50 random patient charts for 99215 claims to validate medical necessity\n2. Site Visit — Physical inspection of facility and patient volume\n3. Beneficiary Interviews — Contact 10–15 patients to verify services\n4. Prepayment Review — Place provider on prepayment edit pending investigation\n\nEstimated timeline: 6–8 weeks. Estimated recovery if confirmed: $2.1M.",
  default: "I can help you analyze specific billing codes, compare this provider to their peers, outline recommended investigative steps, or draft a case summary for your supervisor. What would you like to explore?",
};

// ── MEDICAID-SPECIFIC DATA ────────────────────────────────────────────────────
const medicaidFeed = [
  {id:101,name:'Bright Smiles Dental Group',npi:'3344556677',type:'Billing + Ring',risk:96,conf:91,amt:'$3.4M',flag:'CDT UPCODING · CROWN OVERTREATMENT',days:1,city:'Orlando, FL',spec:'Pediatric Dentistry',status:'Active'},
  {id:102,name:'Sunshine Dental Partners',npi:'4455667788',type:'Billing + Trend',risk:93,conf:88,amt:'$2.7M',flag:'SERVICES NOT RENDERED · PHANTOM BILLING',days:2,city:'Atlanta, GA',spec:'General Dentistry',status:'Active'},
  {id:103,name:'ClearView Vision Center',npi:'5566778899',type:'Network',risk:90,conf:85,amt:'$1.9M',flag:'SELF-REFERRAL · IN-HOUSE OPTICAL LAB',days:3,city:'Dallas, TX',spec:'Optometry',status:'Active'},
  {id:104,name:'Dr. Angela Martinez, DDS',npi:'6677889911',type:'Billing',risk:88,conf:90,amt:'$1.1M',flag:'UNBUNDLING · PROSTHODONTIC PROCEDURES',days:2,city:'Phoenix, AZ',spec:'Prosthodontics',status:'Active'},
  {id:105,name:'Premier Hearing Solutions',npi:'7788990022',type:'Billing + Trend',risk:85,conf:82,amt:'$890K',flag:'NON-QUALIFYING DEVICES · OTC HEARING AIDS',days:5,city:'Houston, TX',spec:'Audiology',status:'Active'},
  {id:106,name:'Family Dental Care LLC',npi:'8899001133',type:'Ring',risk:82,conf:79,amt:'$1.5M',flag:'SHARED ATTRIBUTE RING · MULTI-CLINIC',days:4,city:'Chicago, IL',spec:'General Dentistry',status:'Active'},
  {id:107,name:'Dr. Kevin Park, OD',npi:'9900112244',type:'Trend',risk:78,conf:77,amt:'$620K',flag:'SCOPE OF PRACTICE VIOLATION',days:7,city:'Los Angeles, CA',spec:'Optometry',status:'Cleared'},
  {id:108,name:'Smile Factory Dental',npi:'1011121314',type:'Billing',risk:74,conf:81,amt:'$980K',flag:'UNCERTIFIED TECHNICIAN BILLING · X-RAYS',days:6,city:'Miami, FL',spec:'Pediatric Dentistry',status:'Active'},
];

const cdtCodes = [
  {m:"Mar'23",codes:28,top3:32,bill:35,atRisk:3,owner:'old'},{m:"Apr'23",codes:27,top3:33,bill:37,atRisk:4,owner:'old'},
  {m:"May'23",codes:26,top3:35,bill:39,atRisk:4,owner:'old'},{m:"Jun'23",codes:27,top3:34,bill:38,atRisk:5,owner:'old'},
  {m:"Jul'23",codes:22,top3:42,bill:48,atRisk:22,owner:'new'},{m:"Aug'23",codes:16,top3:55,bill:68,atRisk:48,owner:'new'},
  {m:"Sep'23",codes:12,top3:67,bill:86,atRisk:72,owner:'new'},{m:"Oct'23",codes:9,top3:76,bill:104,atRisk:92,owner:'new'},
  {m:"Nov'23",codes:7,top3:83,bill:122,atRisk:114,owner:'new'},{m:"Dec'23",codes:6,top3:88,bill:138,atRisk:131,owner:'new'},
  {m:"Jan'24",codes:5,top3:92,bill:156,atRisk:150,owner:'new'},{m:"Feb'24",codes:5,top3:94,bill:168,atRisk:162,owner:'new'},
  {m:"Mar'24",codes:5,top3:95,bill:179,atRisk:174,owner:'new'},{m:"Apr'24",codes:5,top3:96,bill:188,atRisk:183,owner:'new'},
  {m:"May'24",codes:5,top3:96,bill:194,atRisk:189,owner:'new'},{m:"Jun'24",codes:5,top3:97,bill:201,atRisk:196,owner:'new'},
  {m:"Jul'24",codes:5,top3:97,bill:207,atRisk:202,owner:'new'},{m:"Aug'24",codes:5,top3:97,bill:214,atRisk:209,owner:'new'},
];

const cdtDist = [
  { code:'D2140', prov:2,  p90:22, med:35 },
  { code:'D2150', prov:3,  p90:18, med:25 },
  { code:'D2740', prov:42, p90:15, med:8  },
  { code:'D2750', prov:38, p90:12, med:6  },
  { code:'D3330', prov:15, p90:8,  med:4  },
];

const cdtTrend = [
  {m:"Mar'23",prov:12,peer:13,owner:'old'},{m:"Apr'23",prov:13,peer:13,owner:'old'},{m:"May'23",prov:12,peer:12,owner:'old'},
  {m:"Jun'23",prov:14,peer:13,owner:'old'},{m:"Jul'23",prov:18,peer:13,owner:'new'},{m:"Aug'23",prov:28,peer:12,owner:'new'},
  {m:"Sep'23",prov:38,peer:13,owner:'new'},{m:"Oct'23",prov:48,peer:12,owner:'new'},{m:"Nov'23",prov:56,peer:13,owner:'new'},
  {m:"Dec'23",prov:63,peer:12,owner:'new'},{m:"Jan'24",prov:68,peer:13,owner:'new'},{m:"Feb'24",prov:71,peer:12,owner:'new'},
  {m:"Mar'24",prov:73,peer:13,owner:'new'},{m:"Apr'24",prov:76,peer:12,owner:'new'},{m:"May'24",prov:77,peer:13,owner:'new'},
  {m:"Jun'24",prov:78,peer:12,owner:'new'},{m:"Jul'24",prov:79,peer:13,owner:'new'},{m:"Aug'24",prov:80,peer:12,owner:'new'},
];

const medicaidNetNodes = [
  { id:'bright', label:'Bright Smiles\nDental Group', x:210, y:135, r:40, color:'#ff4040', risk:96, status:'SUBJECT' },
  { id:'sundn',  label:'Sunshine Dental\nPartners',   x:345, y:55,  r:24, color:'#ff4040', risk:93, status:'FLAGGED' },
  { id:'labco',  label:'ProSmile Dental\nLab LLC',    x:360, y:200, r:20, color:'#f59e0b', risk:80, status:'FLAGGED' },
  { id:'family', label:'Family Dental\nCare LLC',     x:75,  y:200, r:18, color:'#f59e0b', risk:82, status:'FLAGGED' },
  { id:'ortho',  label:'Ortho Plus\nSpecialists',     x:68,  y:65,  r:22, color:'#f59e0b', risk:76, status:'FLAGGED' },
];
const medicaidNetEdges = [
  { from:'bright', to:'sundn',  overlap:41, vol:312, w:4.0 },
  { from:'bright', to:'labco',  overlap:28, vol:245, w:3.2 },
  { from:'bright', to:'family', overlap:22, vol:187, w:2.5 },
  { from:'bright', to:'ortho',  overlap:15, vol:128, w:1.8 },
  { from:'sundn',  to:'labco',  overlap:19, vol:156, w:2.1 },
];
const medicaidNetTable = [
  { name:'Sunshine Dental Partners', npi:'4455667788', spec:'General Dentistry', overlap:41, vol:312, risk:93, status:'FLAGGED' },
  { name:'ProSmile Dental Lab LLC',  npi:'LABCO-001',  spec:'Dental Laboratory', overlap:28, vol:245, risk:80, status:'FLAGGED' },
  { name:'Family Dental Care LLC',   npi:'8899001133', spec:'General Dentistry', overlap:22, vol:187, risk:82, status:'FLAGGED' },
  { name:'Ortho Plus Specialists',   npi:'ORTHO-001',  spec:'Orthodontics',      overlap:15, vol:128, risk:76, status:'FLAGGED' },
];

const medicaidEvLog = [
  {date:'Jul 8, 2023',type:'Ownership Change',icon:'building',text:'Dental practice acquired by Bright Smiles Holdings Corp, a multi-state corporate dental chain. New operational protocols and production targets implemented across all providers.',sev:'info'},
  {date:'Aug 22, 2023',type:'Pattern Alert',icon:'alert',text:'Automated monitoring detected 21% month-over-month increase in crown procedure billing (D2740) — first significant deviation from 14-month baseline. Filling codes (D2140–D2161) declining simultaneously.',sev:'med'},
  {date:'Sep 3, 2024',type:'AI Detection',icon:'bot',text:'Model flagged CDT consolidation pattern — 28 → 5 unique codes over 14 months with 97% concentration in restorative crowns and root canals. Pattern initiated immediately post-acquisition. Crown rate 80% vs. 14% peer median.',sev:'high'},
  {date:'Sep 4, 2024',type:'Ring Detection',icon:'network',text:'Shared-attribute ring identified: Bright Smiles, Sunshine Dental Partners, Family Dental Care share address fragments, phone numbers, and banking info. In-house lab (ProSmile) previously terminated from GA Medicaid enrollment.',sev:'high'},
  {date:'Sep 5, 2024',type:'Credentialing Alert',icon:'alert',text:'3 of 5 rendering staff IDs on radiology claims (D0220/D0230) lack state dental radiography certification. Annual volume of non-certifiable claims: ~$180K.',sev:'med'},
  {date:'Sep 6, 2024',type:'Claims Pull',icon:'file',text:'1,247 crown claims reviewed for FY2024. Crown-to-patient ratio: 4.2 crowns per pediatric patient vs. 0.8 peer median. Estimated overbilling vs. peer-adjusted expected: $3.4M.',sev:'high'},
  {date:'Sep 7, 2024',type:'Analyst Review',icon:'user',text:'Assigned to Analyst J. Morrison. Priority: HIGH. Recommended for chart audit, radiograph review, State MFCU referral, and corporate ownership structure investigation.',sev:'info'},
];

const medicaidPkgSignals = [
  {
    id: 'msig1',
    signal: 'CDT Code Consolidation + Crown Overtreatment',
    icon: TrendingUp, color: C.red,
    anomalyScore: 0.96,
    policies: [
      {
        id: 'MP1',
        source: 'OIG Report OEI-02-14-00250',
        title: 'Questionable Billing for Medicaid Pediatric Dental Services',
        relevance: 96,
        snippet: 'OIG audits found the same billing errors repeated across dental providers — billing for crowns and root canals at rates far exceeding clinical norms. Corporate dental chains showed systematic overtreatment patterns, particularly for pediatric patients, including billing for steel crowns and root canals that were medically unnecessary.',
        ruleType: 'OIG Finding',
      },
      {
        id: 'MP2',
        source: 'State Medicaid Manual §4390',
        title: 'Dental Services Medical Necessity and Coverage Limitations',
        relevance: 91,
        snippet: 'Dental services must be medically necessary. States must have utilization management controls to prevent overuse of restorative services including crowns when less costly alternatives such as fillings would be clinically appropriate. Claims for services that are not medically necessary are not eligible for reimbursement.',
        ruleType: 'Coverage Policy',
      },
      {
        id: 'MP3',
        source: '42 CFR §455.23 — Provider Billing Fraud',
        title: 'Medicaid Provider Billing Requirements and Fraud Prohibitions',
        relevance: 85,
        snippet: 'Claims submitted to Medicaid must accurately represent services provided. Systematic billing for high-cost restorative procedures when simpler services were clinically indicated and delivered constitutes fraudulent billing subject to state recovery action and federal enforcement referral.',
        ruleType: 'Federal Regulation',
      },
    ],
    determination: 'LIKELY VIOLATION',
    determinationConf: 93,
    reasoning: 'CDT code consolidation from 28 to 5 unique codes occurred within 8 months of corporate dental chain acquisition on Jul 8, 2023. Crown procedures (D2740, D2750) now represent 80% of billing vs. 14% peer median for pediatric dental practices. This is directly consistent with OIG OEI-02-14-00250 findings where corporate dental chains drove systematic overtreatment for crowns and root canals. The temporal correlation with acquisition — provider maintained a stable 14-month baseline pre-acquisition — indicates an operational mandate from new ownership rather than clinical evolution.',
    actions: [
      { type: 'IMMEDIATE', label: 'Prior Auth Enforcement', desc: 'Require prior authorization for all D2740/D2750 crown procedure claims from this provider pending investigation.', priority: 'high' },
      { type: 'INVESTIGATION', label: 'Chart Audit — Crown Claims', desc: 'Request radiographs and clinical notes for 50 randomly sampled crown claims. Verify decay severity justifies restorative vs. preventive care under state Medicaid coverage policy.', priority: 'high' },
      { type: 'COMPLIANCE', label: 'State MFCU Referral', desc: 'Refer to State Medicaid Fraud Control Unit given pattern duration, dollar threshold, and corporate chain involvement. Initiate corporate practice of dentistry review.', priority: 'high' },
    ],
    policyGap: 'Most states lack a quantitative crown-to-filling ratio threshold that would trigger automatic prepayment review. OIG findings remain advisory without binding enforcement rules on procedure mix ratios, creating a systematic detection gap for corporate dental chain overtreatment patterns.',
  },
  {
    id: 'msig2',
    signal: 'Shared-Attribute Provider Ring (In-House Lab Self-Referral)',
    icon: Share2, color: C.amber,
    anomalyScore: 0.88,
    policies: [
      {
        id: 'MP4',
        source: '42 CFR §438.608(b)',
        title: 'MCP Provider Enrollment and Network Integrity Requirements',
        relevance: 92,
        snippet: 'MCPs must verify provider enrollment status and ensure all network providers meet state enrollment requirements. Providers sharing addresses, banking, or contact information with terminated or excluded entities must be flagged for additional screening and enrollment verification before claims payment.',
        ruleType: 'Federal Regulation',
      },
      {
        id: 'MP5',
        source: 'Social Security Act §1902(a)(39)',
        title: 'Terminated Provider Exclusion from Medicaid Programs',
        relevance: 86,
        snippet: 'States must terminate from Medicaid participation any provider who has been terminated for cause in Medicare or another state Medicaid program. Network relationships with terminated providers through shared operational infrastructure — including in-house laboratories, dispensaries, and management companies — constitute potential program integrity violations.',
        ruleType: 'Federal Statute',
      },
    ],
    determination: 'POSSIBLE VIOLATION — FURTHER REVIEW REQUIRED',
    determinationConf: 72,
    reasoning: 'Four linked dental entities share address fragments, phone numbers, and banking information consistent with a nominally separate organization operating as a single enterprise. One linked entity (ProSmile Dental Lab LLC) was previously terminated from enrollment in Georgia Medicaid. The in-house lab relationship creates self-referral risk for prosthetic devices including dentures, crowns, and bridges per Medicaid oversight requirements. Determination confidence is 72% pending financial relationship and ownership disclosure review.',
    actions: [
      { type: 'INVESTIGATION', label: 'Ownership Disclosure Review', desc: 'Request 5% ownership/control disclosure for all linked entities. Cross-reference with OIG LEIE, DEX, SSA DMF, and state termination databases.', priority: 'high' },
      { type: 'INVESTIGATION', label: 'In-House Lab Compliance Audit', desc: 'Verify ProSmile Dental Lab enrollment status. Confirm prosthetic devices meet state quality standards and are custom-fitted per Medicaid coverage requirements.', priority: 'med' },
      { type: 'COMPLIANCE', label: 'MCO Network Directory Audit', desc: 'Direct MCO to verify enrollment status of all ring-linked providers against state and federal exclusion lists within 30 days.', priority: 'med' },
    ],
    policyGap: 'No federal standard defines "shared operational infrastructure" as a threshold for ring-detection screening. States vary widely on how they interpret shared-attribute linkages between dental providers and associated labs, creating inconsistent enforcement of in-house lab self-referral prohibitions.',
  },
  {
    id: 'msig3',
    signal: 'Uncertified Technician Billing (Dental Radiography)',
    icon: AlertTriangle, color: C.amber,
    anomalyScore: 0.81,
    policies: [
      {
        id: 'MP6',
        source: 'State Dental Practice Act — Radiograph Administration',
        title: 'Scope of Practice — Dental Radiography Certification Requirements',
        relevance: 94,
        snippet: 'Dental radiographs must be administered by certified dental radiographers or dental hygienists under direct supervision of a licensed dentist. Claims billing Medicaid for x-rays administered by dental assistants who are not appropriately certified to perform radiographic services are not eligible for reimbursement.',
        ruleType: 'State Regulation',
      },
      {
        id: 'MP7',
        source: 'OIG Dental Provider Enforcement Actions (2019–2023, compiled)',
        title: 'Improper Billing by Uncertified Personnel — Enforcement Pattern',
        relevance: 87,
        snippet: 'Past OIG investigations identified dental clinics billing Medicaid for radiographic services (x-rays) performed by dental assistants who were not appropriately certified to administer radiographs, rendering such claims ineligible for reimbursement. Multiple OIG reviews found this error pattern repeated across dental providers in multiple states.',
        ruleType: 'OIG Finding',
      },
    ],
    determination: 'LIKELY VIOLATION',
    determinationConf: 79,
    reasoning: 'Provider bills high volume of D0220/D0230 (periapical/panoramic radiographs) but rendering provider IDs on these claims map to staff without state radiography certification on record. Cross-reference of state dental board certification database shows 3 of 5 rendering technicians lack required certification. State practice act explicitly prohibits Medicaid reimbursement for radiographs administered by uncertified staff, making these claims ineligible regardless of other clinical documentation.',
    actions: [
      { type: 'IMMEDIATE', label: 'Payment Suspension for Uncertified Claims', desc: 'Suspend payment for all D0220/D0230 claims where rendering provider ID maps to staff without confirmed certification, pending verification.', priority: 'high' },
      { type: 'INVESTIGATION', label: 'Certification Cross-Reference', desc: 'Cross-reference all rendering provider IDs submitting radiology claims against state dental board certified radiographer list. Identify full scope of ineligible claims.', priority: 'high' },
      { type: 'COMPLIANCE', label: 'Corrective Action Plan', desc: 'Require provider to submit corrective action plan documenting that all staff administering radiographs hold required state certification before payment resumes.', priority: 'med' },
    ],
    policyGap: 'Automated claims adjudication systems do not routinely cross-check rendering technician certification status against state dental board databases at the time of claim submission. This violation is only detectable through reactive audits, leaving a systematic gap in pre-payment controls.',
  },
];

const medicaidCases = [
  {id:'MCD-2024-0412',prov:'Bright Smiles Dental Group',npi:'3344556677',type:'Billing + Ring',risk:96,status:'Under Review',analyst:'J. Morrison',amt:'$3.4M',date:'Sep 4'},
  {id:'MCD-2024-0408',prov:'Sunshine Dental Partners',npi:'4455667788',type:'Billing + Trend',risk:93,status:'Escalated',analyst:'T. Williams',amt:'$2.7M',date:'Sep 2'},
  {id:'MCD-2024-0395',prov:'ClearView Vision Center',npi:'5566778899',type:'Network',risk:90,status:'Pending',analyst:'Unassigned',amt:'$1.9M',date:'Sep 1'},
  {id:'MCD-2024-0381',prov:'Dr. Angela Martinez, DDS',npi:'6677889911',type:'Billing',risk:88,status:'Under Review',analyst:'M. Johnson',amt:'$1.1M',date:'Aug 28'},
  {id:'MCD-2024-0367',prov:'Premier Hearing Solutions',npi:'7788990022',type:'Billing + Trend',risk:85,status:'Under Review',analyst:'R. Davis',amt:'$890K',date:'Aug 22'},
  {id:'MCD-2024-0354',prov:'Family Dental Care LLC',npi:'8899001133',type:'Ring',risk:82,status:'Closed · Confirmed',analyst:'J. Morrison',amt:'$1.5M',date:'Aug 15'},
  {id:'MCD-2024-0341',prov:'Dr. Kevin Park, OD',npi:'9900112244',type:'Trend',risk:78,status:'Closed · Cleared',analyst:'T. Williams',amt:'—',date:'Aug 10'},
  {id:'MCD-2024-0328',prov:'Smile Factory Dental',npi:'1011121314',type:'Billing',risk:74,status:'Pending',analyst:'Unassigned',amt:'$980K',date:'Aug 20'},
];

const medicaidPolicyGaps = [
  {
    id: 'MG1', severity: 'CRITICAL', title: 'No Crown-to-Filling Ratio Threshold for Automatic Review',
    scope: 'Dental Services — Restorative Coding', affectedProviders: 634, estimatedExposure: '$87M',
    source: 'State Medicaid Manual §4390 / OIG OEI-02-14-00250',
    description: 'No state or federal policy establishes a quantitative crown-to-filling billing ratio that triggers mandatory prepayment review. Corporate dental chains can systematically bill D2740/D2750 crowns in place of D2140/D2150 fillings without automated detection, persisting until a reactive audit is initiated.',
    recommendation: 'Establish a maximum 40% crown-procedure ratio for pediatric dental providers. Trigger prepayment review automatically when exceeded for 3 or more consecutive months.',
    programImpact: 'medicaid',
    casesExposing: 22,
  },
  {
    id: 'MG2', severity: 'HIGH', title: 'No Automated Rendering Technician Certification Cross-Check',
    scope: 'Provider Credentialing — Dental Radiography', affectedProviders: 414, estimatedExposure: '$31M',
    source: 'State Practice Acts / OIG Dental Enforcement (2019–2023)',
    description: 'Claims processing systems do not validate rendering technician IDs on dental radiology claims against state dental board certification databases at adjudication. Billing for radiographs by uncertified staff is undetectable until a reactive audit identifies the pattern.',
    recommendation: 'Implement automated monthly cross-reference between rendering provider IDs on D0220/D0230 claims and state certified radiographer lists. Reject or pend claims where rendering staff certification cannot be confirmed.',
    programImpact: 'medicaid',
    casesExposing: 11,
  },
  {
    id: 'MG3', severity: 'HIGH', title: 'Insufficient MCO Network Provider Enrollment Verification Frequency',
    scope: 'Managed Care — Provider Enrollment Integrity', affectedProviders: 387, estimatedExposure: '$50M',
    source: '42 CFR §438.608(b) / OIG OEI-03-19-00070',
    description: 'MCOs do not consistently verify their network provider directories against state and federal exclusion lists. OIG found nearly 11% of terminated providers remained active in Medicaid networks associated with $50.3M in payments. No required minimum frequency or automated mechanism exists for ongoing reconciliation.',
    recommendation: 'Require monthly automated reconciliation of MCO provider directories against LEIE, DEX, SSA DMF, and state termination databases. Enforce a 30-day remediation SLA with financial penalties for non-compliance.',
    programImpact: 'medicaid',
    casesExposing: 19,
  },
  {
    id: 'MG4', severity: 'MEDIUM', title: 'Medicaid NCCI Edit Lag vs. Medicare',
    scope: 'Claims Processing — NCCI Edits',  affectedProviders: 612, estimatedExposure: '$43M',
    source: 'CMS NCCI Policy Manual / State Medicaid Guidance',
    description: 'Medicaid NCCI edit tables are updated quarterly vs. Medicare\'s monthly cadence, creating a 60–90 day window where new abusive coding patterns can propagate in Medicaid before edits catch up.',
    recommendation: 'Align Medicaid NCCI edit update frequency with Medicare. Implement a rapid-response edit pathway for patterns identified in Medicare fraud cases.',
    programImpact: 'medicaid',
    casesExposing: 19,
  },
];

const medicaidCanned = {
  codes: "The top 5 CDT codes driving 97% of billing are:\n\n• D2740 — Porcelain/ceramic crown (42% of claims)\n• D2750 — Crown, high noble metal (38%)\n• D3330 — Root canal, molar (15%)\n• D0220 — Periapical radiograph (4%)\n• D0230 — Panoramic radiograph (1%)\n\nTypical pediatric dental practices bill 25–30+ unique CDT codes. This consolidation to 5 codes — overwhelmingly crowns — is directly consistent with OIG findings on corporate dental chain overtreatment patterns.",
  compare: "Compared to 412 similar pediatric dental providers in Florida:\n\n• Crown rate (D2740+D2750): 80% vs. peer median 14%\n• Root canal rate (D3330): 15% vs. peer median 4%\n• Filling rate (D2140-D2161): 2% vs. peer median 38%\n• Avg procedures per patient visit: 4.2 vs. 1.8 median\n• Monthly billing growth: +380% over 14 months vs. +8% peer average\n\nThis provider ranks in the top 0.8% statewide for crown utilization in pediatric patients.",
  next: "Recommended investigative steps:\n\n1. Chart Audit — Pull 50 random patient charts with crown claims. Verify radiographs show decay severity justifying crown vs. filling per state Medicaid coverage policy.\n2. State MFCU Referral — Dollar threshold exceeded; refer to Medicaid Fraud Control Unit for corporate practice of dentistry review.\n3. Beneficiary Interviews — Contact 15 beneficiary families to verify services were rendered.\n4. Prior Auth Lock — Require prior authorization for all D2740/D2750 claims from this provider pending investigation outcome.\n5. Lab Compliance — Verify ProSmile Dental Lab enrollment status and prosthetic device quality standards per Medicaid requirements.\n\nEstimated timeline: 8–10 weeks. Estimated recovery if confirmed: $3.4M.",
  default: "I can help you analyze specific CDT billing codes, compare this dental provider to their peer cohort, outline recommended investigative steps, identify ring-linked entities, or draft a case summary for your SIU. What would you like to explore?",
};

// ── SUBCOMPONENTS ──────────────────────────────────────────────────────────────
const mono = { fontFamily: "'IBM Plex Mono', monospace" };
const oxan = { fontFamily: "'Oxanium', sans-serif" };

function RiskBadge({ score }) {
  const color = score >= 90 ? C.red : score >= 75 ? C.amber : C.green;
  const label = score >= 90 ? 'HIGH' : score >= 75 ? 'MED' : 'LOW';
  return (
    <div style={{ display:'flex', alignItems:'center', gap:6 }}>
      <div style={{ width:7, height:7, borderRadius:'50%', background:color, boxShadow:`0 0 6px ${color}` }} />
      <span style={{ ...oxan, fontWeight:700, fontSize:14, color, letterSpacing:'0.03em' }}>
        {score} <span style={{ fontSize:10, fontWeight:500, color:C.muted }}>{label}</span>
      </span>
    </div>
  );
}

function ConfBar({ val, color = C.cyan }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8, width:'100%' }}>
      <div style={{ flex:1, height:3, background:C.b0, borderRadius:2, overflow:'hidden' }}>
        <div style={{ width:`${val}%`, height:'100%', background:color, borderRadius:2 }} />
      </div>
      <span style={{ ...mono, fontSize:10, color:C.dim, minWidth:28 }}>{val}%</span>
    </div>
  );
}

function Chip({ label, color }) {
  return (
    <span style={{
      padding:'2px 8px', borderRadius:4, border:`1px solid ${color}30`,
      background:`${color}10`, fontSize:10, color, ...mono, letterSpacing:'0.04em', whiteSpace:'nowrap',
    }}>{label}</span>
  );
}

function KPICard({ icon: Icon, label, value, sub, color, trend }) {
  return (
    <div style={{
      flex:1, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12,
      padding:'20px 22px', position:'relative', overflow:'hidden',
    }}>
      <div style={{ position:'absolute', top:0, left:0, right:0, height:2,
        background:`linear-gradient(90deg, transparent, ${color}80, transparent)` }} />
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:14 }}>
        <div style={{ padding:8, borderRadius:8, background:`${color}15` }}>
          <Icon size={17} color={color} />
        </div>
        {trend && (
          <div style={{ display:'flex', alignItems:'center', gap:3, fontSize:11, color:C.green }}>
            <ArrowUp size={10} /><span style={mono}>{trend}</span>
          </div>
        )}
      </div>
      <div style={{ ...oxan, fontSize:26, fontWeight:800, color:C.text, lineHeight:1 }}>{value}</div>
      <div style={{ fontSize:12, color:C.dim, marginTop:5 }}>{label}</div>
      {sub && <div style={{ fontSize:11, color:C.muted, marginTop:3 }}>{sub}</div>}
    </div>
  );
}

const tipStyle = { contentStyle:{ background:C.s3, border:`1px solid ${C.b2}`, borderRadius:8, fontSize:11 }, labelStyle:{ color:C.text } };

// ── MEDICAID EXECUTIVE DASHBOARD DATA ────────────────────────────────────────
const cmipPriorities = [
  { label:'Dental / DVH',        active:12,   color:C.red    },
  { label:'Nursing Facilities',  active:4,    color:C.amber  },
  { label:'MCO Capitation',      active:2,    color:C.purple },
  { label:'Provider Enrollment', active:8,    color:C.amber  },
  { label:'Data Analytics',      active:null, status:'Monitoring', color:C.cyan },
];

const stateScorecard = [
  { state:'FL', permError:'8.4%', permUp:true,  mfcuRef:12, capOpen:true,  capDays:47, aiExposure:'$6.1M', status:'CAP OPEN'            },
  { state:'GA', permError:'6.2%', permUp:false, mfcuRef:8,  capOpen:false, capDays:0,  aiExposure:'$4.8M', status:'AT RISK'             },
  { state:'TX', permError:'5.1%', permUp:false, mfcuRef:15, capOpen:false, capDays:0,  aiExposure:'$3.9M', status:'COMPLIANT'           },
  { state:'AZ', permError:'9.7%', permUp:true,  mfcuRef:4,  capOpen:true,  capDays:91, aiExposure:'$2.2M', status:'ESCALATION PENDING'  },
  { state:'IL', permError:'4.8%', permUp:false, mfcuRef:11, capOpen:false, capDays:0,  aiExposure:'$1.8M', status:'COMPLIANT'           },
  { state:'OH', permError:'7.3%', permUp:false, mfcuRef:6,  capOpen:false, capDays:0,  aiExposure:'$2.6M', status:'AT RISK'             },
];

const medicaidServiceLines = [
  { line:'Dental (Pediatric)',   aiExposure:11.2, stateRpt:2.1, trend:'up',   gap:'CRITICAL' },
  { line:'Vision / DMEPOS',     aiExposure:7.8,  stateRpt:3.4, trend:'flat', gap:'HIGH'     },
  { line:'Nursing Facilities',  aiExposure:5.1,  stateRpt:5.0, trend:'down', gap:'LOW'      },
  { line:'MCO Improper Cap.',   aiExposure:4.5,  stateRpt:0.2, trend:'up',   gap:'CRITICAL' },
  { line:'Provider Enrollment', aiExposure:3.2,  stateRpt:0.8, trend:'up',   gap:'HIGH'     },
];

const medicaidTrend = [
  {m:'Sep',a:110,s:1.8,stateRpt:0.3},{m:'Oct',a:138,s:2.2,stateRpt:0.4},
  {m:'Nov',a:152,s:2.5,stateRpt:0.5},{m:'Dec',a:171,s:2.9,stateRpt:0.5},
  {m:'Jan',a:195,s:3.3,stateRpt:0.6},{m:'Feb',a:218,s:3.7,stateRpt:0.7},
  {m:'Mar',a:234,s:4.0,stateRpt:0.7},{m:'Apr',a:256,s:4.4,stateRpt:0.8},
  {m:'May',a:278,s:4.8,stateRpt:0.9},{m:'Jun',a:295,s:5.1,stateRpt:0.9},
  {m:'Jul',a:312,s:5.4,stateRpt:1.0},{m:'Aug',a:338,s:5.9,stateRpt:1.1},
];

const stateGapData = [
  { state:'FL', ai:6.1, rpt:0.9 },
  { state:'GA', ai:4.8, rpt:0.7 },
  { state:'TX', ai:3.9, rpt:1.2 },
  { state:'AZ', ai:2.2, rpt:0.2 },
  { state:'IL', ai:1.8, rpt:0.8 },
  { state:'OH', ai:2.6, rpt:0.3 },
];

// ── MEDICAID EXECUTIVE DASHBOARD ──────────────────────────────────────────────
function MedicaidDashboard() {
  const statusColor = (s) => s === 'COMPLIANT' ? C.green : s === 'AT RISK' ? C.amber : C.red;
  const gapColor    = (g) => g === 'CRITICAL' ? C.red : g === 'HIGH' ? C.amber : C.green;
  const trendIcon   = (t) => t === 'up' ? '↑' : t === 'down' ? '↓' : '→';

  return (
    <div style={{ padding:24, display:'flex', flexDirection:'column', gap:20 }}>

      {/* ── CMIP Priority Alignment Strip ─────────────────────────────────── */}
      <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:'13px 22px' }} className="fu">
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:10 }}>
          <div style={{ fontSize:10, color:C.muted, ...mono, letterSpacing:'0.08em' }}>
            CMS COMPREHENSIVE MEDICAID INTEGRITY PLAN · FY2024–2028 PRIORITY COVERAGE
          </div>
          <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
            {cmipPriorities.map((p, i) => (
              <div key={i} style={{
                display:'flex', alignItems:'center', gap:7,
                padding:'5px 12px', borderRadius:20,
                border:`1px solid ${p.color}40`, background:`${p.color}10`,
              }}>
                <div style={{
                  width:6, height:6, borderRadius:'50%', background:p.color,
                  boxShadow:`0 0 6px ${p.color}`,
                  animation: p.active ? 'pkgPulse 2s ease-in-out infinite' : 'none',
                }} />
                <span style={{ fontSize:11, color:p.color, fontWeight:600 }}>{p.label}</span>
                <span style={{ ...mono, fontSize:10, color:C.dim }}>
                  {p.active != null ? `${p.active} active` : p.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── KPI Row ────────────────────────────────────────────────────────── */}
      <div style={{ display:'flex', gap:14 }} className="fu">
        <KPICard icon={User}          label="Beneficiaries at Risk"      value="94,200" sub="Enrolled with flagged providers · this quarter"        color={C.red}    trend="+9% QoQ"  />
        <KPICard icon={DollarSign}    label="Improper Payment Exposure"   value="$28.6M" sub="Est. per GAO PERM methodology"                         color={C.green}  trend="+18% QoQ" />
        <KPICard icon={Globe}         label="States Engaged"              value="18"     sub="Active findings / TA guidance issued"                  color={C.purple} trend="+3 QoQ"   />
        <KPICard icon={ClipboardList} label="CMIP Priority Coverage"      value="4 of 5" sub="FY2024–28 integrity priorities w/ active signals"      color={C.amber}  />
      </div>

      {/* ── Trend Chart + Service Line Heatmap ────────────────────────────── */}
      <div style={{ display:'flex', gap:14 }}>
        {/* Exposure Trend */}
        <div style={{ flex:2, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
          <div style={{ marginBottom:18 }}>
            <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text }}>Medicaid Program Exposure Trend</div>
            <div style={{ fontSize:11, color:C.dim, marginTop:3 }}>AI-detected exposure vs. state-reported findings ($M) · Sep 2023 – Aug 2024</div>
          </div>
          <ResponsiveContainer width="100%" height={190}>
            <AreaChart data={medicaidTrend} margin={{ top:5, right:10, bottom:0, left:-18 }}>
              <defs>
                <linearGradient id="gME" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.green}  stopOpacity={0.35}/>
                  <stop offset="95%" stopColor={C.green} stopOpacity={0.02}/>
                </linearGradient>
                <linearGradient id="gMR" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.amber}  stopOpacity={0.30}/>
                  <stop offset="95%" stopColor={C.amber} stopOpacity={0.02}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={C.b0} />
              <XAxis dataKey="m" tick={{ fill:C.muted, fontSize:10, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:C.muted, fontSize:10, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <Tooltip {...tipStyle} />
              <Area type="monotone" dataKey="s"        stroke={C.green} strokeWidth={2} fill="url(#gME)" name="AI Exposure ($M)"       />
              <Area type="monotone" dataKey="stateRpt" stroke={C.amber} strokeWidth={2} strokeDasharray="5 3" fill="url(#gMR)" name="State-Reported ($M)" />
            </AreaChart>
          </ResponsiveContainer>
          <div style={{ display:'flex', gap:20, marginTop:10 }}>
            {[{c:C.green,l:'AI-Detected Exposure'},{c:C.amber,l:'State-Reported Findings',dash:true}].map((lg,i) => (
              <div key={i} style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:C.dim }}>
                <div style={{ width:20, height:2, background:lg.c, borderRadius:1, opacity:0.9,
                  borderTop: lg.dash ? `2px dashed ${lg.c}` : 'none', borderBottom:'none', borderLeft:'none', borderRight:'none' }} />
                {lg.l}
              </div>
            ))}
          </div>
        </div>

        {/* Service Line Heatmap */}
        <div style={{ flex:1, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
          <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text, marginBottom:4 }}>Service Line Risk</div>
          <div style={{ fontSize:11, color:C.dim, marginBottom:16 }}>AI exposure vs. state-reported ($M)</div>
          <div style={{ display:'flex', flexDirection:'column', gap:0 }}>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 52px 52px 68px', gap:6, paddingBottom:9, borderBottom:`1px solid ${C.b0}` }}>
              {['Service','AI $M','State $M','Gap'].map((h, i) => (
                <div key={i} style={{ fontSize:9, color:C.muted, ...mono, textAlign: i > 0 ? 'right' : 'left' }}>{h}</div>
              ))}
            </div>
            {medicaidServiceLines.map((sl, i) => (
              <div key={i} style={{
                display:'grid', gridTemplateColumns:'1fr 52px 52px 68px', gap:6,
                padding:'10px 0', borderBottom:`1px solid ${C.b0}20`, alignItems:'center',
              }}>
                <div style={{ fontSize:11, color:C.text }}>
                  {sl.line}
                  <span style={{ marginLeft:5, fontSize:10, color: sl.trend==='up' ? C.red : sl.trend==='down' ? C.green : C.dim }}>
                    {trendIcon(sl.trend)}
                  </span>
                </div>
                <div style={{ ...mono, fontSize:11, color:C.green, textAlign:'right' }}>{sl.aiExposure}</div>
                <div style={{ ...mono, fontSize:11, color:C.amber, textAlign:'right' }}>{sl.stateRpt}</div>
                <div style={{ textAlign:'right' }}>
                  <span style={{
                    padding:'2px 7px', borderRadius:4, fontSize:9, ...mono,
                    color:gapColor(sl.gap), background:`${gapColor(sl.gap)}15`,
                    border:`1px solid ${gapColor(sl.gap)}30`,
                  }}>{sl.gap}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── State Performance Scorecard ────────────────────────────────────── */}
      <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
          <div>
            <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text }}>State Performance Scorecard</div>
            <div style={{ fontSize:11, color:C.dim, marginTop:3 }}>
              State first-line-of-defense accountability · 6 highest-exposure states monitored
            </div>
          </div>
          <div style={{ fontSize:9, color:C.muted, ...mono, letterSpacing:'0.06em' }}>SORTED BY AI-FLAGGED EXPOSURE ↓</div>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'56px 130px 130px 150px 120px 1fr', gap:10,
          paddingBottom:10, borderBottom:`1px solid ${C.b0}`, marginBottom:4 }}>
          {['STATE','PERM ERROR RATE','MFCU REFERRALS','CAP STATUS','AI EXPOSURE','OVERSIGHT STATUS'].map((h, i) => (
            <div key={i} style={{ fontSize:9, color:C.muted, ...mono, letterSpacing:'0.05em' }}>{h}</div>
          ))}
        </div>
        {stateScorecard.map((s, i) => {
          const sc = statusColor(s.status);
          return (
            <div key={i} style={{
              display:'grid', gridTemplateColumns:'56px 130px 130px 150px 120px 1fr', gap:10,
              padding:'10px 0', borderBottom:`1px solid ${C.b0}15`, alignItems:'center',
            }}>
              <div style={{ ...oxan, fontSize:16, fontWeight:700, color:C.text }}>{s.state}</div>
              <div style={{ display:'flex', alignItems:'center', gap:5 }}>
                <span style={{ ...mono, fontSize:12, color: s.permUp ? C.red : C.green }}>{s.permError}</span>
                <span style={{ fontSize:11, color: s.permUp ? C.red : C.green }}>{s.permUp ? '↑' : '↓'}</span>
              </div>
              <div style={{ ...mono, fontSize:12, color:C.text }}>{s.mfcuRef} referrals</div>
              <div>
                {s.capOpen
                  ? <span style={{ fontSize:10, color:C.red, ...mono }}>OPEN · {s.capDays}d outstanding</span>
                  : <span style={{ fontSize:10, color:C.green, ...mono }}>None active</span>
                }
              </div>
              <div style={{ ...mono, fontSize:13, color:C.purple, fontWeight:600 }}>{s.aiExposure}</div>
              <div>
                <span style={{
                  padding:'3px 10px', borderRadius:4, fontSize:10, ...mono, fontWeight:600,
                  color:sc, background:`${sc}15`, border:`1px solid ${sc}40`,
                  animation: s.status === 'ESCALATION PENDING' ? 'pkgPulse 2s ease-in-out infinite' : 'none',
                }}>{s.status}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Accountability Gap + MCO Network Integrity ─────────────────────── */}
      <div style={{ display:'flex', gap:14 }}>

        {/* Accountability Gap */}
        <div style={{ flex:1, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
          <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text, marginBottom:4 }}>Federal–State Accountability Gap</div>
          <div style={{ fontSize:11, color:C.dim, marginBottom:18 }}>
            CMS AI-detected vs. state self-reported exposure · same reporting period
          </div>
          {/* Summary callout */}
          <div style={{ background:C.s3, border:`1px solid ${C.b1}`, borderRadius:10, padding:'14px 18px', marginBottom:18 }}>
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:8 }}>
              <span style={{ fontSize:11, color:C.dim }}>AI-Identified Exposure</span>
              <span style={{ ...mono, fontSize:13, fontWeight:600, color:C.green }}>$28.6M</span>
            </div>
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:10 }}>
              <span style={{ fontSize:11, color:C.dim }}>State-Reported (same period)</span>
              <span style={{ ...mono, fontSize:13, fontWeight:600, color:C.amber }}>$4.1M</span>
            </div>
            <div style={{ height:1, background:C.b1, marginBottom:10 }} />
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <span style={{ fontSize:12, fontWeight:600, color:C.text }}>Accountability Gap</span>
              <span style={{ ...mono, fontSize:16, fontWeight:700, color:C.red }}>$24.5M</span>
            </div>
            <div style={{ fontSize:10, color:C.amber, marginTop:8 }}>
              ⚠ 5 states recommended for targeted federal review
            </div>
          </div>
          <ResponsiveContainer width="100%" height={155}>
            <BarChart data={stateGapData} margin={{ top:5, right:10, bottom:0, left:-18 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.b0} />
              <XAxis dataKey="state" tick={{ fill:C.muted, fontSize:10, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:C.muted, fontSize:10, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <Tooltip {...tipStyle} />
              <Bar dataKey="ai"  fill={C.purple} radius={[3,3,0,0]} name="AI-Detected ($M)"    opacity={0.85} />
              <Bar dataKey="rpt" fill={C.amber}  radius={[3,3,0,0]} name="State-Reported ($M)" opacity={0.85} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* MCO Network Integrity */}
        <div style={{ flex:1, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
          <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text, marginBottom:4 }}>MCO Network Integrity</div>
          <div style={{ fontSize:11, color:C.dim, marginBottom:18 }}>
            Managed care plan oversight metrics · 42 CFR §438.608(b) compliance
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {[
              { label:'Terminated Provider Re-entry Rate', value:'11%',      threshold:'> 5% alert threshold',  status:'ABOVE THRESHOLD', color:C.red,   pct:55  },
              { label:'Network Dir. Reconciliation Lag',   value:'43 days',  threshold:'> 30d alert threshold',  status:'HIGH',            color:C.amber, pct:48  },
              { label:'Capitation vs. Enrollment Accuracy',value:'94.2%',    threshold:'≥ 95% compliance target',status:'BELOW TARGET',    color:C.amber, pct:94  },
            ].map((m, i) => (
              <div key={i} style={{ background:C.s3, borderRadius:10, padding:'14px 16px' }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:8 }}>
                  <div style={{ fontSize:12, color:C.text, flex:1, paddingRight:10, lineHeight:1.4 }}>{m.label}</div>
                  <div style={{ textAlign:'right', flexShrink:0 }}>
                    <div style={{ ...mono, fontSize:17, fontWeight:700, color:m.color, lineHeight:1 }}>{m.value}</div>
                    <span style={{
                      display:'inline-block', marginTop:4,
                      padding:'2px 8px', borderRadius:3, fontSize:9, ...mono,
                      color:m.color, background:`${m.color}15`, border:`1px solid ${m.color}30`,
                    }}>{m.status}</span>
                  </div>
                </div>
                <div style={{ fontSize:10, color:C.muted, marginBottom:6 }}>{m.threshold}</div>
                <div style={{ height:3, background:C.b0, borderRadius:2, overflow:'hidden' }}>
                  <div style={{ width:`${m.pct}%`, height:'100%', background:m.color, borderRadius:2, opacity:0.8 }} />
                </div>
              </div>
            ))}
          </div>
          <div style={{ marginTop:14, padding:'10px 14px', background:`${C.amber}08`, border:`1px solid ${C.amber}20`, borderRadius:8 }}>
            <div style={{ fontSize:10, color:C.amber, lineHeight:1.5 }}>
              Source: OIG OEI-03-19-00070 — 11% terminated provider re-entry rate linked to $50.3M in improper payments. No federal minimum reconciliation frequency currently mandated.
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}

// ── DASHBOARD ──────────────────────────────────────────────────────────────────
function Dashboard({ prog }) {
  if (prog === 'medicaid') return <MedicaidDashboard />;

  const pd = programs[prog];
  const ac = pd.color;
  const analysts = [
    { name:'J. Morrison', active:8, pending:3, closed:24, load:73 },
    { name:'T. Williams', active:6, pending:5, closed:19, load:55 },
    { name:'M. Johnson',  active:9, pending:2, closed:31, load:82 },
    { name:'R. Davis',    active:4, pending:6, closed:18, load:48 },
    { name:'Unassigned',  active:0, pending:12,closed:0,  load:0  },
  ];

  return (
    <div style={{ padding:24, display:'flex', flexDirection:'column', gap:20 }}>
      {/* KPIs */}
      <div style={{ display:'flex', gap:14 }} className="fu">
        <KPICard icon={AlertTriangle} label="Flagged Providers" value={pd.kpis.flagged} sub="Active anomalies · this quarter" color={C.red} trend="+12% QoQ" />
        <KPICard icon={DollarSign} label="Potential Recovery" value={pd.kpis.savings} sub="Est. recoverable overpayments" color={C.green} trend="+18% QoQ" />
        <KPICard icon={CheckCircle} label="Cases Resolved" value={pd.kpis.resolved} sub="Closed this quarter" color={ac} trend="+8% QoQ" />
        <KPICard icon={Zap} label="Avg AI Confidence" value={pd.kpis.confidence} sub="Across active detections" color={C.amber} />
      </div>

      {/* Charts row */}
      <div style={{ display:'flex', gap:14 }}>
        <div style={{ flex:2, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:18 }}>
            <div>
              <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text }}>Anomaly Detection Trend</div>
              <div style={{ fontSize:11, color:C.dim, marginTop:3 }}>Monthly flagged providers & estimated savings ($M) · Sep 2023 – Aug 2024</div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={190}>
            <AreaChart data={pd.trend} margin={{ top:5, right:10, bottom:0, left:-18 }}>
              <defs>
                <linearGradient id="gA" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={ac} stopOpacity={0.35}/>
                  <stop offset="95%" stopColor={ac} stopOpacity={0.02}/>
                </linearGradient>
                <linearGradient id="gS" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.green} stopOpacity={0.35}/>
                  <stop offset="95%" stopColor={C.green} stopOpacity={0.02}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={C.b0} />
              <XAxis dataKey="m" tick={{ fill:C.muted, fontSize:10, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill:C.muted, fontSize:10, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <Tooltip {...tipStyle} />
              <Area type="monotone" dataKey="a" stroke={ac} strokeWidth={2} fill="url(#gA)" name="Flagged Providers" />
              <Area type="monotone" dataKey="s" stroke={C.green} strokeWidth={2} fill="url(#gS)" name="Savings ($M)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div style={{ flex:1, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
          <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text, marginBottom:4 }}>Recovery by Category</div>
          <div style={{ fontSize:11, color:C.dim, marginBottom:18 }}>Potential recovery ($M)</div>
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={pd.cats} layout="vertical" margin={{ top:0, right:10, bottom:0, left:-10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.b0} horizontal={false} />
              <XAxis type="number" tick={{ fill:C.muted, fontSize:10, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <YAxis dataKey="n" type="category" tick={{ fill:C.dim, fontSize:10, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} width={90} />
              <Tooltip {...tipStyle} />
              <Bar dataKey="v" fill={ac} radius={[0,4,4,0]} name="$M" opacity={0.85} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Queue */}
      <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
        <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text, marginBottom:16 }}>Investigator Queue Health</div>
        <div style={{ display:'flex', gap:12 }}>
          {analysts.map((a,i) => (
            <div key={i} style={{ flex:1, background:C.s3, border:`1px solid ${C.b0}`, borderRadius:10, padding:14 }}>
              <div style={{ fontSize:12, fontWeight:600, color:C.text, marginBottom:10 }}>{a.name}</div>
              <div style={{ display:'flex', gap:10, marginBottom:12 }}>
                {[{v:a.active,l:'Active',c:C.cyan},{v:a.pending,l:'Pending',c:C.amber},{v:a.closed,l:'Closed',c:C.green}].map((x,j) => (
                  <div key={j} style={{ textAlign:'center', flex:1 }}>
                    <div style={{ ...oxan, fontSize:20, fontWeight:700, color:x.c }}>{x.v}</div>
                    <div style={{ fontSize:9, color:C.muted, marginTop:1 }}>{x.l}</div>
                  </div>
                ))}
              </div>
              {a.load > 0 && (
                <>
                  <div style={{ fontSize:10, color:C.muted, marginBottom:5 }}>Capacity {a.load}%</div>
                  <div style={{ height:4, background:C.b0, borderRadius:2, overflow:'hidden' }}>
                    <div style={{ width:`${a.load}%`, height:'100%', borderRadius:2,
                      background: a.load > 80 ? C.red : a.load > 60 ? C.amber : C.green }} />
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── ANOMALY FEED ──────────────────────────────────────────────────────────────
function AnomalyFeed({ prog = 'medicare', onSelect, feedback = {}, onFeedback = () => {} }) {
  const [expanded, setExpanded] = useState(null);
  const [filter, setFilter] = useState('All');
  const types = ['All','Billing','Network','Trend'];
  const activeFeed = prog === 'medicaid' ? medicaidFeed : feed;
  
  // Helper to get latest feedback for provider
  const getLatestFeedback = (npi) => {
    if (!feedback[npi] || !feedback[npi].overall) return null;
    return feedback[npi].overall[0];
  };
  
  let rows = filter === 'All' ? activeFeed : activeFeed.filter(r => r.type.includes(filter));

  return (
    <div style={{ padding:24, display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div>
          <div style={{ ...oxan, fontSize:18, fontWeight:700, color:C.text }}>Anomaly Detection Feed</div>
          <div style={{ fontSize:12, color:C.dim, marginTop:3 }}>{rows.length} of {activeFeed.length} alerts · sorted by risk score</div>
        </div>
        <div style={{ display:'flex', gap:10 }}>
          <div style={{ display:'flex', gap:5, alignItems:'center' }}>
            <span style={{ fontSize:10, color:C.muted, ...mono, marginRight:3 }}>ANOMALY TYPE:</span>
            {types.map(t => (
              <button key={t} onClick={() => setFilter(t)} style={{
                padding:'5px 12px', borderRadius:5, border:`1px solid ${filter===t ? C.cyan : C.b1}`,
                background: filter===t ? `${C.cyan}15` : 'transparent',
                color: filter===t ? C.cyan : C.dim, fontSize:11, cursor:'pointer',
              }}>{t}</button>
            ))}
          </div>
        </div>
      </div>

      {/* Column headers */}
      <div style={{
        display:'grid', gridTemplateColumns:'2.2fr 1fr 110px 110px 80px 160px',
        padding:'8px 16px', background:C.s3, borderRadius:7, border:`1px solid ${C.b0}`,
        ...mono, fontSize:10, color:C.muted, letterSpacing:'0.06em',
      }}>
        <span>PROVIDER / SIGNAL</span><span>ANOMALY TYPE</span>
        <span>RISK SCORE</span><span>AI CONFIDENCE</span><span>AT RISK</span><span>ACTION</span>
      </div>

      {rows.map((r, i) => {
        const fb = getLatestFeedback(r.npi);
        const fbColor = fb ? (fb.verdict === 'confirmed' ? C.red : fb.verdict === 'legitimate' ? C.green : fb.verdict === 'watch' ? C.cyan : C.amber) : null;
        const isCleared = r.status === 'Cleared';
        return (
          <div key={r.id} className="fu" style={{
            background:C.s2, border:`1px solid ${expanded===r.id ? C.b2 : (fb ? fbColor+'40' : C.b0)}`,
            borderRadius:10, overflow:'hidden',
            animationDelay:`${i*0.04}s`,
            opacity: isCleared ? 0.5 : 1,
          }}>
          <div onClick={() => setExpanded(expanded===r.id ? null : r.id)} style={{
            display:'grid', gridTemplateColumns:'2.2fr 1fr 110px 110px 80px 160px',
            padding:'14px 16px', cursor:'pointer', alignItems:'center',
          }}>
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <div style={{ fontSize:14, fontWeight:500, color:C.text }}>{r.name}</div>
                {isCleared && (
                  <div style={{ padding:'2px 7px', borderRadius:4, background:`${C.green}15`, border:`1px solid ${C.green}30`, fontSize:9, color:C.green, ...mono, display:'flex', alignItems:'center', gap:4 }}>
                    <CheckCircle size={9}/>
                    CLEARED
                  </div>
                )}
                {fb && !isCleared && (
                  <div style={{ padding:'2px 7px', borderRadius:4, background:`${fbColor}15`, border:`1px solid ${fbColor}30`, fontSize:9, color:fbColor, ...mono, display:'flex', alignItems:'center', gap:4 }}>
                    {fb.verdict === 'confirmed' ? <AlertCircle size={9}/> : fb.verdict === 'legitimate' ? <CheckCircle size={9}/> : <Clock size={9}/>}
                    {fb.verdict === 'confirmed' ? 'CONFIRMED' : fb.verdict === 'legitimate' ? 'LEGITIMATE' : fb.verdict === 'watch' ? 'ON WATCH' : 'REVIEW'}
                  </div>
                )}
              </div>
              <div style={{ ...mono, fontSize:10, color:C.muted, marginTop:2 }}>NPI: {r.npi} · {r.city} · {r.spec}</div>
              <div style={{ marginTop:6 }}>
                <Chip label={r.flag} color={C.red} />
              </div>
              {fb && fb.comment && (
                <div style={{ marginTop:5, fontSize:10, color:C.dim, fontStyle:'italic' }}>
                  "{fb.comment}" — {fb.investigator?.name}
                </div>
              )}
            </div>
            <div style={{ fontSize:12, color:C.dim }}>{r.type}</div>
            <RiskBadge score={r.risk} />
            <ConfBar val={r.conf} />
            <div style={{ ...oxan, fontSize:13, fontWeight:700, color:isCleared ? C.dim : C.amber }}>{isCleared ? '—' : r.amt}</div>
            <div style={{ display:'flex', gap:7 }}>
              {isCleared ? (
                <button disabled style={{
                  padding:'5px 11px', borderRadius:6, border:`1px solid ${C.b0}`,
                  background:C.s3, color:C.muted, fontSize:11, cursor:'not-allowed',
                }}>Closed</button>
              ) : (
                <button onClick={e=>{e.stopPropagation(); onSelect(r);}} style={{
                  padding:'5px 11px', borderRadius:6, border:`1px solid ${C.cyan}50`,
                  background:`${C.cyan}10`, color:C.cyan, fontSize:11, cursor:'pointer',
                }}>Review</button>
              )}
            </div>
          </div>
          {expanded === r.id && (
            <div style={{ borderTop:`1px solid ${C.b0}`, padding:16, background:C.s3 }}>
              {isCleared ? (
                <div style={{ display:'flex', gap:10, alignItems:'flex-start' }}>
                  <div style={{ padding:6, borderRadius:6, background:`${C.green}15`, flexShrink:0 }}>
                    <CheckCircle size={14} color={C.green} />
                  </div>
                  <div>
                    <div style={{ ...mono, fontSize:10, color:C.green, letterSpacing:'0.06em', marginBottom:7 }}>
                      CASE CLOSED · NO FURTHER ACTION REQUIRED
                    </div>
                    <div style={{ fontSize:13, color:C.dim, lineHeight:1.7 }}>
                      This case has been reviewed and <span style={{ color:C.green, fontWeight:500 }}>cleared</span> by investigator.
                      Initial anomaly flags were determined to have legitimate clinical explanations.{' '}
                      <span style={{ color:C.text }}>Status: Closed · Cleared</span> — No recovery action or escalation needed.
                      Case file available for audit reference in Case Management.
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ display:'flex', gap:10, alignItems:'flex-start' }}>
                  <div style={{ padding:6, borderRadius:6, background:`${C.cyan}15`, flexShrink:0 }}>
                    <Bot size={14} color={C.cyan} />
                  </div>
                  <div>
                    <div style={{ ...mono, fontSize:10, color:C.cyan, letterSpacing:'0.06em', marginBottom:7 }}>
                      AI ANALYSIS · INLINE REASON CODE
                    </div>
                    <div style={{ fontSize:13, color:C.dim, lineHeight:1.7 }}>
                      This provider shows statistically significant deviation from peer cohort.
                      Primary signal: <span style={{ color:C.text, fontWeight:500 }}>{r.flag.toLowerCase()}</span> — detected with{' '}
                      <span style={{ color:C.cyan }}>{r.conf}% confidence</span> using ensemble anomaly detection across 12-month claims history.
                      Flagged {r.days} day{r.days>1?'s':''} ago.{' '}
                      <span style={{ color:C.amber }}>Recommended: Priority investigation + records request.</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
          </div>
        );
      })}
    </div>
  );
}

// ── PROVIDER DEEP-DIVE ────────────────────────────────────────────────────────
function ProviderDive({ provider, prog, feedback = {}, onFeedback = () => {} }) {
  const [tab, setTab] = useState('signals');
  const ac = programs[prog].color;
  const p = provider || (prog === 'medicaid' ? medicaidFeed[0] : feed[0]);
  const providerId = p.npi;
  const isMedicaid = prog === 'medicaid';
  const activeHcpcs = isMedicaid ? cdtCodes : hcpcs;
  const activeEmDist = isMedicaid ? cdtDist : emDist;
  const activeEmTrend = isMedicaid ? cdtTrend : emTrend;
  const activeNetNodes = isMedicaid ? medicaidNetNodes : netNodes;
  const activeNetEdges = isMedicaid ? medicaidNetEdges : netEdges;
  const activeNetTable = isMedicaid ? medicaidNetTable : netTable;
  const activePkgSignals = isMedicaid ? medicaidPkgSignals : pkgSignals;
  const activeEvLog = isMedicaid ? medicaidEvLog : evLog;
  const verdictOptions = [
    { value: 'confirmed', label: 'Confirmed Issue', color: C.red, desc: 'AI flags are accurate — this pattern warrants escalation or formal investigation' },
    { value: 'legitimate', label: 'Legitimate Case', color: C.green, desc: 'Flagged patterns have valid explanations — case can be closed with documentation' },
    { value: 'review', label: 'Needs Further Review', color: C.amber, desc: 'Insufficient information to make final determination — additional investigation required' },
    { value: 'watch', label: 'On Watch', color: C.cyan, desc: 'Not actionable now but warrants continued monitoring for emerging patterns' },
  ];
  // Helper to get latest feedback for section
  function latest(section) {
    if (!feedback[providerId]) return null;
    if (section === 'overall') return feedback[providerId].overall?.[0] || null;
    return feedback[providerId].components?.[section]?.[0] || null;
  }
  // Helper to get all feedback for section
  function allFeedback(section) {
    if (!feedback[providerId]) return [];
    if (section === 'overall') return feedback[providerId].overall || [];
    return feedback[providerId].components?.[section] || [];
  }

  // Feedback UI for a section (component-level: agree/disagree/review)
  function ComponentFeedback({ section, label }) {
    const [verdict, setVerdict] = useState('');
    const [comment, setComment] = useState('');
    const [showComment, setShowComment] = useState(false);
    const [show, setShow] = useState(false);
    const [pendingVerdict, setPendingVerdict] = useState(null);
    const last = latest(section);
    const componentOptions = [
      { value: 'agree', label: 'Confirms Issue', icon: XCircle, selectedColor: C.red },
      { value: 'disagree', label: 'Legitimate', icon: CheckCircle, selectedColor: C.green },
      { value: 'review', label: 'Needs Review', icon: Clock, selectedColor: C.amber },
    ];
    
    const handleVote = (vote) => {
      setPendingVerdict(vote);
    };
    
    const handleSave = () => {
      if (pendingVerdict) {
        onFeedback(providerId, section, pendingVerdict, comment);
        setVerdict(pendingVerdict);
        setPendingVerdict(null);
        setComment('');
        setShowComment(false);
      }
    };
    
    const currentColor = componentOptions.find(opt => opt.value === pendingVerdict)?.selectedColor || C.cyan;
    
    return (
      <div style={{ marginTop: 12, padding:'10px 12px', background:`${C.s3}90`, border:`1px solid ${C.b0}`, borderRadius:6 }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ fontSize:11, color:C.muted, ...mono }}>YOUR ASSESSMENT:</span>
            {componentOptions.map(opt => {
              const Icon = opt.icon;
              const isSelected = last?.verdict === opt.value;
              const isPending = pendingVerdict === opt.value;
              const displayColor = isSelected ? opt.selectedColor : (isPending ? opt.selectedColor : C.muted);
              return (
                <button key={opt.value} onClick={() => handleVote(opt.value)}
                  style={{ padding:'4px 10px', borderRadius:5, border:`1px solid ${(isSelected || isPending) ? opt.selectedColor+'80' : C.b1}`, 
                    background:(isSelected || isPending)?`${opt.selectedColor}20`:'transparent', color:displayColor, fontSize:10, cursor:'pointer',
                    display:'flex', alignItems:'center', gap:5 }}>
                  <Icon size={11}/> {opt.label}
                </button>
              );
            })}
            <button onClick={() => setShowComment(c => !c)}
              style={{ padding:'4px 10px', borderRadius:5, border:`1px solid ${C.b1}`, background:'transparent', 
                color:C.cyan, fontSize:10, cursor:'pointer', display:'flex', alignItems:'center', gap:4 }}>
              + Comment
            </button>
            {pendingVerdict && (
              <button onClick={handleSave}
                style={{ padding:'4px 12px', borderRadius:5, border:`1px solid ${currentColor}`, background:`${currentColor}30`, 
                  color:currentColor, fontSize:10, cursor:'pointer', fontWeight:600, display:'flex', alignItems:'center', gap:4 }}>
                <CheckCircle size={11}/> Save
              </button>
            )}
          </div>
          {allFeedback(section).length > 0 && (
            <button onClick={()=>setShow(s=>!s)} style={{ fontSize:10, color:C.cyan, background:'none', border:'none', cursor:'pointer', ...mono }}>
              {show ? 'HIDE' : 'SHOW'} HISTORY ({allFeedback(section).length})
            </button>
          )}
        </div>
        {showComment && (
          <div style={{ marginTop:8 }}>
            <input
              type="text"
              placeholder="Add optional comment..."
              value={comment}
              onChange={e => setComment(e.target.value)}
              style={{ fontSize:11, padding:'6px 10px', borderRadius:5, border:`1px solid ${C.b1}`, width:'100%', background:C.s2, color:C.text }}
            />
          </div>
        )}
        {last && (
          <div style={{ fontSize:10, color:C.dim, marginTop:6, paddingTop:6, borderTop:`1px solid ${C.b0}` }}>
            <b style={{ color:componentOptions.find(v=>v.value===last.verdict)?.selectedColor }}>{componentOptions.find(v=>v.value===last.verdict)?.label}</b>
            {last.comment && <> · <span style={{ fontStyle:'italic' }}>"{last.comment}"</span></>}
            <span style={{ marginLeft:8 }}>— {last.investigator?.name} · {last.timestamp?.slice(11,16)}</span>
          </div>
        )}
        {show && allFeedback(section).length > 1 && (
          <div style={{ marginTop:6, fontSize:9, color:C.muted, paddingTop:6, borderTop:`1px solid ${C.b0}` }}>
            <div style={{ marginBottom:4, ...mono }}>HISTORY:</div>
            {allFeedback(section).slice(1).map((f,i) => (
              <div key={i} style={{ marginBottom:3, paddingLeft:8 }}>
                <b style={{ color:componentOptions.find(v=>v.value===f.verdict)?.selectedColor }}>{componentOptions.find(v=>v.value===f.verdict)?.label}</b>
                {f.comment && <> · {f.comment}</>}
                <span style={{ marginLeft:6, color:C.muted }}>— {f.investigator?.name} · {f.timestamp?.slice(0,16).replace('T',' ')}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Overall case-level feedback
  function OverallFeedback() {
    const [selectedVerdict, setSelectedVerdict] = useState('');
    const [comment, setComment] = useState('');
    const [confirmed, setConfirmed] = useState(false);
    const last = latest('overall');
    
    // Check for conflicting feedback - get list of signals marked as "Confirms Issue"
    const confirmedIssueSignals = reasons.filter(r => {
      const compFb = latest(r.section);
      return compFb && compFb.verdict === 'agree'; // 'agree' value now means "Confirms Issue"
    });
    const hasConfirmedIssues = confirmedIssueSignals.length > 0;
    
    // Show consistency check if user selects "Legitimate Case" but has confirmed issue signals
    const showConsistencyCheck = selectedVerdict === 'legitimate' && hasConfirmedIssues;
    
    const handleSubmit = () => {
      if (!selectedVerdict) {
        return; // Do nothing if no verdict selected
      }
      
      // Validate: if has confirmed issues but marking as legitimate, require comment and confirmation
      if (hasConfirmedIssues && selectedVerdict === 'legitimate') {
        if (!comment || !confirmed) {
          return; // Prevent submission without notes and checkbox
        }
      }
      
      onFeedback(providerId, 'overall', selectedVerdict, comment);
      setComment('');
      setConfirmed(false);
      setSelectedVerdict('');
    };
    
    const currentColor = verdictOptions.find(opt => opt.value === selectedVerdict)?.color || C.cyan;
    
    return (
      <div style={{ marginTop:16, padding:'14px 16px', background:`${C.cyan}08`, border:`1px solid ${C.cyan}20`, borderRadius:8 }}>
        <div style={{ ...mono, fontSize:10, color:C.cyan, letterSpacing:'0.07em', marginBottom:10 }}>INVESTIGATOR JUDGEMENT - FINAL RULING</div>
        
        {/* Radio button options with descriptions */}
        <div style={{ display:'flex', flexDirection:'column', gap:8, marginBottom:12 }}>
          {verdictOptions.map(opt => {
            const isSelected = selectedVerdict === opt.value;
            const isPreviouslySelected = last?.verdict === opt.value;
            const displayColor = isSelected ? opt.color : (isPreviouslySelected ? opt.color : C.muted);
            return (
              <label key={opt.value} style={{ cursor:'pointer' }}>
                <div style={{ 
                  padding:'8px 14px', borderRadius:6, border:`1px solid ${isSelected ? opt.color+'90' : C.b1}`, 
                  background:isSelected?`${opt.color}22`:'transparent', 
                  display:'flex', alignItems:'flex-start', gap:10
                }}>
                  <input 
                    type="radio" 
                    name="verdict" 
                    value={opt.value}
                    checked={isSelected}
                    onChange={() => setSelectedVerdict(opt.value)}
                    style={{ marginTop:3, cursor:'pointer' }}
                  />
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:12, fontWeight:600, color:displayColor, marginBottom:2 }}>{opt.label}</div>
                    <div style={{ fontSize:10, color:isSelected ? opt.color : C.dim, fontWeight:400, lineHeight:1.4 }}>{opt.desc}</div>
                  </div>
                </div>
              </label>
            );
          })}
        </div>
        
        <input
          type="text"
          placeholder={showConsistencyCheck ? "Notes required to resolve consistency check" : "Add notes (optional)"}
          value={comment}
          onChange={e => setComment(e.target.value)}
          style={{ fontSize:12, padding:'8px 12px', borderRadius:6, border:`1px solid ${showConsistencyCheck ? C.amber : C.b1}`, width:'100%', background:C.s2, color:C.text, marginBottom:10 }}
        />
        
        {/* Consistency Check - shows immediately when Legitimate Case is selected with confirmed issue signals */}
        {showConsistencyCheck && (
          <div style={{ marginBottom:10, fontSize:11, color:C.amber, background:`${C.amber}10`, border:`1px solid ${C.amber}30`, borderRadius:6, padding:'10px 12px' }}>
            <div style={{ display:'flex', alignItems:'flex-start', gap:6, marginBottom:8 }}>
              <AlertCircle size={14} style={{ flexShrink:0, marginTop:1 }}/>
              <div>
                <div style={{ fontWeight:700, marginBottom:4, fontSize:12 }}>⚠️ Consistency Check Required</div>
                <div style={{ fontSize:10, lineHeight:1.6, marginBottom:8 }}>
                  You marked the following signal{confirmedIssueSignals.length > 1 ? 's' : ''} as "<span style={{ color:C.red, fontWeight:600 }}>Confirms Issue</span>" but are marking this case as "<span style={{ color:C.green, fontWeight:600 }}>Legitimate Case</span>":
                </div>
                <div style={{ marginLeft:12, marginBottom:10 }}>
                  {confirmedIssueSignals.map((sig, i) => (
                    <div key={i} style={{ fontSize:10, color:C.text, marginBottom:3, display:'flex', alignItems:'center', gap:6 }}>
                      <div style={{ width:5, height:5, borderRadius:'50%', background:sig.color }}/>
                      <b>{sig.label}</b>
                    </div>
                  ))}
                </div>
                <div style={{ background:C.s2, border:`1px solid ${C.amber}40`, borderRadius:6, padding:'8px 10px' }}>
                  <label style={{ display:'flex', alignItems:'flex-start', gap:8, cursor:'pointer', fontSize:10 }}>
                    <input 
                      type="checkbox" 
                      checked={confirmed} 
                      onChange={e => setConfirmed(e.target.checked)}
                      style={{ marginTop:2, cursor:'pointer' }}
                    />
                    <span style={{ flex:1, lineHeight:1.5 }}>
                      <b>I confirm this case is legitimate despite the flagged signals.</b> I have entered notes above explaining why the AI signals do not indicate fraud in this specific case.
                    </span>
                  </label>
                </div>
              </div>
            </div>
          </div>
        )}
        
        {/* Submit button */}
        <button 
          onClick={handleSubmit}
          disabled={!selectedVerdict || (showConsistencyCheck && (!comment || !confirmed))}
          style={{ 
            padding:'10px 20px', borderRadius:6, border:`1px solid ${selectedVerdict ? currentColor : C.b1}`, 
            background:selectedVerdict ? `${currentColor}30` : C.s3, 
            color:selectedVerdict ? currentColor : C.muted, 
            fontSize:13, cursor:(selectedVerdict && (!showConsistencyCheck || (comment && confirmed))) ? 'pointer' : 'not-allowed',
            fontWeight:600, ...oxan, width:'100%',
            opacity: (selectedVerdict && (!showConsistencyCheck || (comment && confirmed))) ? 1 : 0.5
          }}>
          Submit Assessment
        </button>
        
        {last && (
          <div style={{ marginTop:10, fontSize:11, color:C.dim, paddingTop:8, borderTop:`1px solid ${C.cyan}20` }}>
            <b style={{ color:verdictOptions.find(v=>v.value===last.verdict)?.color }}>{verdictOptions.find(v=>v.value===last.verdict)?.label}</b>
            {last.comment && <> · <span style={{ fontStyle:'italic' }}>"{last.comment}"</span></>}
            <span style={{ marginLeft:8 }}>— {last.investigator?.name} · {last.timestamp?.slice(0,19).replace('T',' ')}</span>
          </div>
        )}
      </div>
    );
  }

  const reasons = isMedicaid ? [
    { icon:TrendingUp, label:'CDT Code Consolidation + Crown Overtreatment', color:C.red,
      desc:`Unique CDT procedure codes fell from 28 → 5 following Jul 2023 corporate acquisition. Prior 14-month baseline showed stable diversity (26–28 codes). Crown procedures (D2740, D2750) now represent 80% of billing vs. 14% peer median for pediatric dental. Pattern change timing correlates directly with acquisition.`, section:'hcpcs_consolidation' },
    { icon:AlertTriangle, label:'High-Cost Code Upcoding vs. Peers', color:C.amber,
      desc:`Crown rate was normal (12-14%) pre-acquisition, then spiked to 80% over 14 months. Current rate is 5.7× peer median. Both code consolidation and crown upcoding exhibit synchronized timing with ownership change on Jul 8, 2023, suggesting coordinated operational changes under new management.`, section:'em_upcoding' },
    { icon:Share2, label:'Shared-Attribute Ring / In-House Lab Self-Referral', color:C.amber,
      desc:`4 linked dental entities share address fragments, phone numbers, banking info. In-house lab (ProSmile Dental Lab) was previously terminated from GA Medicaid. Patient overlap across linked clinics: 41% with Sunshine Dental Partners. Creates self-referral risk for prosthetic devices (crowns, dentures, bridges).`, section:'network_cobilling' },
  ] : [
    { icon:TrendingUp, label:'HCPCS Consolidation', color:C.red,
      desc:`Unique procedure codes fell from 45 → 6 following July 2023 ownership transfer. Prior 16-month baseline showed stable diversity (44-47 codes). Top 3 codes now represent 98% of billing, up from 41% at transfer. Pattern change timing correlates with ownership change.`, section:'hcpcs_consolidation' },
    { icon:AlertTriangle, label:'E&M Upcoding', color:C.amber,
      desc:`99215 rate was normal (19-21%) pre-ownership change, then spiked 311% to 78% over 12 months. Current rate is 4.3× peer median. Both signals exhibit synchronized timing with ownership transfer on July 15, 2023, suggesting coordinated operational changes.`, section:'em_upcoding' },
    { icon:Share2, label:'Network Co-billing', color:C.amber,
      desc:`34% of patients share treatment history with Sunrise Medical Group (also flagged, NPI 9876543210). Mutual referral density is 4.2× expected for independent practices.`, section:'network_cobilling' },
  ];

  return (
    <div style={{ padding:24, display:'flex', flexDirection:'column', gap:18 }}>
      {/* Header */}
      <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
          <div style={{ display:'flex', gap:14, alignItems:'center' }}>
            <div style={{ width:52, height:52, borderRadius:11, background:`${C.red}15`, border:`1px solid ${C.red}30`, display:'flex', alignItems:'center', justifyContent:'center' }}>
              <Building size={24} color={C.red} />
            </div>
            <div>
              <div style={{ ...oxan, fontSize:21, fontWeight:800, color:C.text }}>{p.name}</div>
              <div style={{ fontSize:12, color:C.dim, marginTop:3 }}>{p.spec} · {p.city} · NPI: {p.npi}</div>
              <div style={{ display:'flex', gap:7, marginTop:8 }}>
                <Chip label="HIGH RISK" color={C.red} />
                <Chip label={p.type.toUpperCase()} color={C.amber} />
                <Chip label={`FLAGGED ${p.days}D AGO`} color={C.cyan} />
                <Chip label={programs[prog].label.toUpperCase()} color={programs[prog].color} />
              </div>
            </div>
          </div>
          <div style={{ textAlign:'right' }}>
            <div style={{ ...oxan, fontSize:54, fontWeight:800, color:C.red, lineHeight:1 }}>{p.risk}</div>
            <div style={{ ...mono, fontSize:10, color:C.muted, marginTop:2 }}>RISK SCORE / 100</div>
            <div style={{ marginTop:10, width:140 }}>
              <ConfBar val={p.conf} color={C.red} />
              <div style={{ ...mono, fontSize:9, color:C.muted, marginTop:3, textAlign:'right' }}>AI CONFIDENCE</div>
            </div>
          </div>
        </div>
      </div>

      {/* AI Reason Codes */}
      <div style={{ background:`${C.cyan}06`, border:`1px solid ${C.cyan}18`, borderRadius:12, padding:18 }} className="fu">
        <div style={{ display:'flex', gap:12, alignItems:'flex-start' }}>
          <div style={{ padding:9, borderRadius:9, background:`${C.cyan}15`, flexShrink:0 }}>
            <Bot size={18} color={C.cyan} />
          </div>
          <div style={{ flex:1 }}>
            <div style={{ ...mono, fontSize:10, color:C.cyan, letterSpacing:'0.07em', marginBottom:12 }}>
              AI ANALYSIS · {reasons.length} ANOMALY SIGNALS DETECTED
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:13 }}>
              {reasons.map((r, i) => (
                <div key={i} style={{ display:'flex', gap:10, alignItems:'flex-start', borderBottom:`1px solid ${C.b1}30`, paddingBottom:8, marginBottom:8 }}>
                  <r.icon size={18} color={r.color} style={{ marginTop:2 }}/>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:13, fontWeight:600, color:r.color }}>{r.label}</div>
                    <div style={{ fontSize:12, color:C.text, marginTop:2 }}>{r.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display:'flex', borderBottom:`1px solid ${C.b0}` }}>
        {[
          { id:'signals', label:'Signal Explanation' },
          { id:'policy',   label:'Policy Analysis', badge:true },
          { id:'evidence', label:'Evidence Log' },
          { id:'timeline', label:'Billing Timeline' },
        ].map(t => (
          <button key={t.id} onClick={()=>setTab(t.id)} style={{
            padding:'10px 22px', border:'none', background:'transparent',
            color: tab===t.id ? ac : C.muted,
            borderBottom:`2px solid ${tab===t.id ? ac : 'transparent'}`,
            ...oxan, fontSize:12, fontWeight:700, cursor:'pointer',
            textTransform:'uppercase', letterSpacing:'0.07em', marginBottom:-1,
            display:'flex', alignItems:'center', gap:7,
          }}>
            {t.label}
            {t.badge && <span style={{ marginLeft:6, background:C.cyan, color:'#fff', borderRadius:4, fontSize:9, padding:'1px 5px' }}>BETA</span>}
          </button>
        ))}
      </div>

      {tab === 'signals' && (
        <div style={{ display:'flex', flexDirection:'column', gap:16 }}>

          {/* ── SIGNAL 1: HCPCS CODE CONSOLIDATION ─────────────────────────── */}
          <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, overflow:'hidden' }}>
            <div style={{ padding:'14px 20px', background:`${C.red}08`, borderBottom:`1px solid ${C.b0}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                <div style={{ width:24, height:24, borderRadius:6, background:`${C.red}20`, display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <TrendingUp size={13} color={C.red}/>
                </div>
                <div>
                  <div style={{ ...oxan, fontWeight:700, fontSize:13, color:C.text }}>Signal 1 · HCPCS Code Consolidation</div>
                  <div style={{ fontSize:11, color:C.dim, marginTop:1 }}>Billing collapsed from 45 unique codes to 6 codes — 98% concentration on just 3 high-paying codes. Drastic shift correlates directly with July 2023 ownership transfer to Pain Management Holdings LLC.</div>
                </div>
              </div>
              <Chip label="HIGH SEVERITY" color={C.red}/>
            </div>
            <div style={{ padding:20, display:'flex', gap:16 }}>
              {/* Left: Dual-axis chart (2/3 width) */}
              <div style={{ flex:2, display:'flex', flexDirection:'column' }}>
                <div style={{ fontSize:11, color:C.muted, marginBottom:12, ...mono }}>{isMedicaid ? 'CDT CODE DIVERSITY COLLAPSE & CONCENTRATION RISE · 18-MONTH TREND · ACQUISITION JUL 8, 2023' : 'CODE DIVERSITY COLLAPSE & CONCENTRATION RISE · 18-MONTH TREND · OWNERSHIP CHANGE JUL 15, 2023'}</div>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={activeHcpcs} margin={{ top:5, right:40, bottom:5, left:-20 }}>
                    <defs>
                      <linearGradient id="gCodes" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={C.red} stopOpacity={0.4}/>
                        <stop offset="95%" stopColor={C.red} stopOpacity={0.02}/>
                      </linearGradient>
                      <linearGradient id="gConc" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={C.amber} stopOpacity={0.2}/>
                        <stop offset="95%" stopColor={C.amber} stopOpacity={0.02}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.b0} />
                    <XAxis dataKey="m" tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} interval={3}/>
                    <YAxis yAxisId="left" tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} domain={[0,50]}/>
                    <YAxis yAxisId="right" orientation="right" tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} domain={[0,100]} tickFormatter={v=>`${v}%`}/>
                    <Tooltip {...tipStyle} formatter={(v, name)=>[name === 'Unique Codes' ? `${v} codes` : `${v}%`, name]}/>
                    <Area yAxisId="left" type="monotone" dataKey="codes" stroke={C.red} strokeWidth={2.5} fill="url(#gCodes)" name="Unique Codes"/>
                    <Area yAxisId="right" type="monotone" dataKey="top3" stroke={C.amber} strokeWidth={1.5} fill="url(#gConc)" name="Top 3 Concentration" strokeDasharray="4 3"/>
                    {/* Ownership change marker */}
                    <line x1="23%" y1="0" x2="23%" y2="100%" stroke={C.cyan} strokeWidth={2} strokeDasharray="6 4" opacity={0.6}/>
                    <text x="24%" y="15" fill={C.cyan} fontSize={9} fontFamily="IBM Plex Mono" fontWeight={600}>OWNERSHIP CHANGE</text>
                    <text x="24%" y="28" fill={C.dim} fontSize={8} fontFamily="IBM Plex Mono">Jul 15, 2023</text>
                  </AreaChart>
                </ResponsiveContainer>
                <div style={{ display:'flex', gap:14, marginTop:8 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:C.dim }}>
                    <div style={{ width:14, height:2, background:C.red }}/> {isMedicaid ? 'Unique CDT Codes (28 → 5)' : 'Unique HCPCS Codes (47 → 6)'}
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:C.dim }}>
                    <div style={{ width:14, height:2, background:C.amber }}/> Top 3 Code Concentration ({isMedicaid ? '32% → 97%' : '38% → 98%'})
                  </div>
                </div>
              </div>

              {/* Right: Metrics + Table (1/3 width) */}
              <div style={{ flex:1, display:'flex', flexDirection:'column', gap:12 }}>
                {/* Key metrics */}
                <div style={{ display:'flex', flexDirection:'row', gap:10 }}>
                  {[
                    {v: isMedicaid ? '28 → 5' : '45 → 6', l:'Code diversity collapse', c:C.red, sub: isMedicaid ? '82% drop post-acquisition' : '87% drop post-ownership'},
                    {v: isMedicaid ? '97%' : '98%', l:'Top 3 concentration', c:C.amber, sub: isMedicaid ? 'up from 32% at acquisition' : 'up from 41% at transfer'},
                  ].map((s,i)=>(
                    <div key={i} style={{ background:C.s3, border:`1px solid ${C.b0}`, borderRadius:8, padding:'12px 14px', flex:1 }}>
                      <div style={{ ...oxan, fontSize:20, fontWeight:800, color:s.c, lineHeight:1 }}>{s.v}</div>
                      <div style={{ fontSize:10, color:C.dim, marginTop:5, lineHeight:1.3 }}>{s.l}</div>
                      <div style={{ fontSize:9, color:C.muted, marginTop:2 }}>{s.sub}</div>
                    </div>
                  ))}
                </div>

                {/* Top 6 codes table */}
                <div style={{ flex:1, background:C.s3, border:`1px solid ${C.b0}`, borderRadius:8, padding:'12px 14px', display:'flex', flexDirection:'column' }}>
                  <div style={{ fontSize:10, color:C.muted, marginBottom:10, ...mono }}>{isMedicaid ? 'TOP 5 CDT CODES · CURRENT MIX' : 'TOP 6 CODES · CURRENT MIX'}</div>
                  <div style={{ display:'flex', flexDirection:'column', gap:6, flex:1 }}>
                    {(isMedicaid ? [
                      {code:'D2740', name:'Porcelain/ceramic crown', pct:42},
                      {code:'D2750', name:'Crown, high noble metal', pct:38},
                      {code:'D3330', name:'Root canal, molar', pct:15},
                      {code:'D0220', name:'Periapical radiograph', pct:4},
                      {code:'D0230', name:'Panoramic radiograph', pct:1},
                    ] : [
                      {code:'99215', name:'Office visit, level 5', pct:42},
                      {code:'99214', name:'Office visit, level 4', pct:35},
                      {code:'99213', name:'Office visit, level 3', pct:21},
                      {code:'96372', name:'Therapeutic injection', pct:1.2},
                      {code:'36415', name:'Venipuncture', pct:0.5},
                      {code:'85025', name:'CBC', pct:0.3},
                    ]).map((row,i, arr)=>(
                      <div key={i} style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', paddingBottom:5, borderBottom: i < arr.length-1 ? `1px solid ${C.b0}` : 'none' }}>
                        <div style={{ display:'flex', flexDirection:'column', gap:1 }}>
                          <span style={{ ...mono, fontSize:11, fontWeight:700, color:C.text }}>{row.code}</span>
                          <span style={{ fontSize:9, color:C.dim, lineHeight:1.2 }}>{row.name}</span>
                        </div>
                        <span style={{ ...mono, fontSize:11, fontWeight:700, color:i<3 ? C.red : C.muted, marginLeft:8 }}>{row.pct}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            {/* Component-level feedback for Signal 1 */}
            <div style={{ padding:'0 20px 16px 20px' }}>
              <ComponentFeedback section="hcpcs_consolidation" label={isMedicaid ? 'CDT Code Consolidation Signal' : 'HCPCS Code Consolidation Signal'} />
            </div>
          </div>

          {/* ── SIGNAL 2: E&M UPCODING ─────────────────────────────────────── */}
          <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, overflow:'hidden' }}>
            <div style={{ padding:'14px 20px', background:`${C.amber}08`, borderBottom:`1px solid ${C.b0}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                <div style={{ width:24, height:24, borderRadius:6, background:`${C.amber}20`, display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <AlertTriangle size={13} color={C.amber}/>
                </div>
                <div>
                  <div style={{ ...oxan, fontWeight:700, fontSize:13, color:C.text }}>{isMedicaid ? 'Signal 2 · High-Cost Code Upcoding vs. Peers' : 'Signal 2 · E&M Level Upcoding'}</div>
                  <div style={{ fontSize:11, color:C.dim, marginTop:1 }}>{isMedicaid ? 'Crown procedures (D2740/D2750) used at 5.7× peer median — clinically improbable in pediatric dental without systematic overtreatment. Rate was normal (12-14%) pre-acquisition, then spiked to 80% over 14 months.' : '99215 (highest complexity) used 4× above peer median — statistically improbable without systematic miscoding. Provider maintained normal 19-21% rate until ownership transfer, then spiked 311% over 12 months.'}</div>
                </div>
              </div>
              <Chip label="HIGH SEVERITY" color={C.amber}/>
            </div>
            <div style={{ padding:20, display:'flex', gap:16 }}>
              {/* E&M distribution grouped bar */}
              <div style={{ flex:1 }}>
                <div style={{ fontSize:11, color:C.muted, marginBottom:12, ...mono }}>{isMedicaid ? 'CDT CODE MIX — THIS PROVIDER vs. PEERS · % OF ALL RESTORATIVE CLAIMS' : 'E&M CODE MIX — THIS PROVIDER vs. PEERS · % OF ALL E&M CLAIMS'}</div>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={activeEmDist} margin={{ top:5, right:10, bottom:5, left:-20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.b0} />
                    <XAxis dataKey="code" tick={{ fill:C.dim, fontSize:10, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false}/>
                    <YAxis tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} tickFormatter={v=>`${v}%`}/>
                    <Tooltip {...tipStyle} formatter={(v)=>[`${v}%`]}/>
                    <Bar dataKey="prov" name="This Provider" fill={C.red} radius={[3,3,0,0]} opacity={0.9}/>
                    <Bar dataKey="p90"  name="90th Pct Peer" fill={C.amber} radius={[3,3,0,0]} opacity={0.6}/>
                    <Bar dataKey="med"  name="Peer Median"   fill={C.cyan} radius={[3,3,0,0]} opacity={0.35}/>
                  </BarChart>
                </ResponsiveContainer>
                <div style={{ display:'flex', gap:14, marginTop:8 }}>
                  {[{c:C.red,l:'This Provider'},{c:C.amber,l:'90th Pct Peer'},{c:C.cyan,l:'Peer Median'}].map((x,i)=>(
                    <div key={i} style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:C.dim }}>
                      <div style={{ width:9, height:9, borderRadius:2, background:x.c }}/>{x.l}
                    </div>
                  ))}
                </div>
              </div>
              {/* 99215 rate trend */}
              <div style={{ flex:1 }}>
                <div style={{ fontSize:11, color:C.muted, marginBottom:12, ...mono }}>{isMedicaid ? 'CROWN RATE (D2740+D2750) OVER TIME · ACQUISITION JUL 8, 2023' : '99215 UTILIZATION RATE OVER TIME · OWNERSHIP CHANGE JUL 15, 2023'}</div>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={activeEmTrend} margin={{ top:5, right:10, bottom:5, left:-20 }}>
                    <defs>
                      <linearGradient id="gProv" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={C.red} stopOpacity={0.4}/>
                        <stop offset="95%" stopColor={C.red} stopOpacity={0.02}/>
                      </linearGradient>
                      <linearGradient id="gPeer" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={C.cyan} stopOpacity={0.2}/>
                        <stop offset="95%" stopColor={C.cyan} stopOpacity={0.02}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={C.b0} />
                    <XAxis dataKey="m" tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} interval={3}/>
                    <YAxis tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} tickFormatter={v=>`${v}%`} domain={[0,90]}/>
                    <Tooltip {...tipStyle} formatter={(v)=>[`${v}%`]}/>
                    <Area type="monotone" dataKey="prov" stroke={C.red} strokeWidth={2.5} fill="url(#gProv)" name="This Provider"/>
                    <Area type="monotone" dataKey="peer" stroke={C.cyan} strokeWidth={1.5} fill="url(#gPeer)" name="Peer Median" strokeDasharray="4 3"/>
                    {/* Ownership change marker */}
                    <line x1="23%" y1="0" x2="23%" y2="100%" stroke={C.cyan} strokeWidth={2} strokeDasharray="6 4" opacity={0.6}/>
                    <text x="24%" y="15" fill={C.cyan} fontSize={9} fontFamily="IBM Plex Mono" fontWeight={600}>OWNERSHIP CHANGE</text>
                    <text x="24%" y="28" fill={C.dim} fontSize={8} fontFamily="IBM Plex Mono">Jul 15, 2023</text>
                  </AreaChart>
                </ResponsiveContainer>
                <div style={{ display:'flex', gap:14, marginTop:8 }}>
                  {[
                    {c:C.red,l: isMedicaid ? 'This Provider (13% → 80%)' : 'This Provider (19% → 78%)'},
                    {c:C.cyan,l: isMedicaid ? 'Peer Median (stable ~13%)' : 'Peer Median (stable ~19%)'},
                  ].map((x,i)=>(
                    <div key={i} style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:C.dim }}>
                      <div style={{ width:14, height:2, background:x.c }}/>{x.l}
                    </div>
                  ))}
                </div>
              </div>
              {/* Stats panel */}
              <div style={{ width:160, display:'flex', flexDirection:'column', gap:9 }}>
                {(isMedicaid ? [
                  {v:'80%', l:'Provider crown rate', c:C.red, sub:'vs 14% peer median'},
                  {v:'Top 0.8%', l:'Statewide crown utilization', c:C.red, sub:'among 412 peers (FL)'},
                  {v:'+466%', l:'Rate rise post-acquisition', c:C.amber, sub:'13% → 80% in 14mo'},
                  {v:'$3.4M', l:'Est. crown overbilling', c:C.amber, sub:'vs. peer-adjusted expected'},
                ] : [
                  {v:'78%', l:'Provider 99215 rate', c:C.red, sub:'vs 18% peer median'},
                  {v:'Top 1.3%', l:'Nationally for 99215', c:C.red, sub:'among 847 peers (FL)'},
                  {v:'+311%', l:'Rate rise post-transfer', c:C.amber, sub:'19% → 78% in 12mo'},
                  {v:'$1.1M', l:'Est. E&M overbilling', c:C.amber, sub:'vs. peer-adjusted expected'},
                ]).map((s,i)=>(
                  <div key={i} style={{ background:C.s3, border:`1px solid ${C.b0}`, borderRadius:8, padding:'10px 12px' }}>
                    <div style={{ ...oxan, fontSize:18, fontWeight:800, color:s.c, lineHeight:1 }}>{s.v}</div>
                    <div style={{ fontSize:10, color:C.dim, marginTop:4, lineHeight:1.4 }}>{s.l}</div>
                    <div style={{ fontSize:9, color:C.muted, marginTop:2 }}>{s.sub}</div>
                  </div>
                ))}
              </div>
            </div>
            {/* Component-level feedback for Signal 2 */}
            <div style={{ padding:'0 20px 16px 20px' }}>
              <ComponentFeedback section="em_upcoding" label={isMedicaid ? 'High-Cost Code Upcoding Signal' : 'E&M Upcoding Signal'} />
            </div>
          </div>

          {/* ── CROSS-SIGNAL AI INSIGHT: SYNCHRONIZED TIMING ─────────────── */}
          <div style={{ padding:'14px 18px', background:`${C.purple}08`, border:`1px solid ${C.purple}22`, borderRadius:10, display:'flex', gap:12, alignItems:'flex-start' }}>
            <div style={{ padding:8, borderRadius:8, background:`${C.purple}15`, flexShrink:0 }}>
              <Lightbulb size={16} color={C.purple}/>
            </div>
            <div style={{ flex:1 }}>
              <div style={{ ...oxan, fontSize:12, fontWeight:700, color:C.purple, marginBottom:5 }}>AI PATTERN CORRELATION INSIGHT</div>
              <div style={{ fontSize:12, color:C.dim, lineHeight:1.7 }}>
                Both <b style={{ color:C.text }}>{isMedicaid ? 'Signal 1 (CDT consolidation)' : 'Signal 1 (HCPCS consolidation)'}</b> and <b style={{ color:C.text }}>{isMedicaid ? 'Signal 2 (crown upcoding)' : 'Signal 2 (E&M upcoding)'}</b> exhibit synchronized timing — pattern changes initiated within <b style={{ color:C.purple }}>{isMedicaid ? '30 days of corporate acquisition' : '30 days of ownership transfer'}</b> on {isMedicaid ? 'July 8, 2023' : 'July 15, 2023'}. The provider maintained a stable {isMedicaid ? '14' : '16'}-month baseline under original ownership with normal code diversity and {isMedicaid ? 'restorative' : 'E&M'} distribution. This temporal correlation suggests <b style={{ color:C.purple }}>systematic operational changes under new management</b> rather than gradual clinical evolution, strengthening the inference of {isMedicaid ? 'a coordinated overtreatment mandate from corporate ownership post-acquisition.' : 'a coordinated billing optimization strategy post-acquisition.'}
              </div>
            </div>
          </div>

          {/* ── SIGNAL 3: NETWORK CO-BILLING ───────────────────────────────── */}
          <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, overflow:'hidden' }}>
            <div style={{ padding:'14px 20px', background:`${C.amber}08`, borderBottom:`1px solid ${C.b0}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                <div style={{ width:24, height:24, borderRadius:6, background:`${C.amber}20`, display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <Share2 size={13} color={C.amber}/>
                </div>
                <div>
                  <div style={{ ...oxan, fontWeight:700, fontSize:13, color:C.text }}>{isMedicaid ? 'Signal 3 · Shared-Attribute Ring / In-House Lab Self-Referral' : 'Signal 3 · Suspicious Network Co-billing'}</div>
                  <div style={{ fontSize:11, color:C.dim, marginTop:1 }}>{isMedicaid ? '4 linked dental entities — shared addresses, phone numbers, and banking — with in-house lab previously terminated from GA Medicaid' : '4 connected providers — all independently flagged — with anomalous shared-patient overlap rates'}</div>
                </div>
              </div>
              <Chip label="MEDIUM SEVERITY" color={C.amber}/>
            </div>
            <div style={{ padding:20, display:'flex', gap:16 }}>
              {/* SVG Network Diagram */}
              <div style={{ flex:1 }}>
                <div style={{ fontSize:11, color:C.muted, marginBottom:12, ...mono }}>{isMedicaid ? 'DENTAL PROVIDER RING · SHARED ATTRIBUTES & PATIENT OVERLAP · EDGE WIDTH = SHARED PATIENT OVERLAP %' : 'PROVIDER CO-BILLING NETWORK · EDGE WIDTH = SHARED PATIENT OVERLAP %'}</div>
                <div style={{ background:C.s3, border:`1px solid ${C.b0}`, borderRadius:10, overflow:'hidden', position:'relative' }}>
                  <svg viewBox="0 0 435 275" width="100%" style={{ display:'block' }}>
                    {/* Grid background lines */}
                    {[50,100,150,200,250,300,350,400].map(x=>(
                      <line key={`vg${x}`} x1={x} y1={0} x2={x} y2={275} stroke={C.b0} strokeWidth={0.5} opacity={0.5}/>
                    ))}
                    {[50,100,150,200,250].map(y=>(
                      <line key={`hg${y}`} x1={0} y1={y} x2={435} y2={y} stroke={C.b0} strokeWidth={0.5} opacity={0.5}/>
                    ))}
                    {/* Edges */}
                    {activeNetEdges.map((e,i)=>{
                      const f = activeNetNodes.find(n=>n.id===e.from);
                      const t = activeNetNodes.find(n=>n.id===e.to);
                      const subjectId = isMedicaid ? 'bright' : 'aps';
                      const mx = (f.x+t.x)/2, my = (f.y+t.y)/2;
                      return (
                        <g key={i}>
                          <line x1={f.x} y1={f.y} x2={t.x} y2={t.y}
                            stroke={e.from===subjectId||e.to===subjectId ? C.purple : C.muted}
                            strokeWidth={e.w} opacity={0.45} strokeDasharray={e.from!==subjectId&&e.to!==subjectId?'4 3':undefined}/>
                          <rect x={mx-14} y={my-8} width={28} height={15} rx={3}
                            fill={C.s1} stroke={C.b1} strokeWidth={0.8}/>
                          <text x={mx} y={my+4} textAnchor="middle"
                            fill={C.dim} fontSize={8} fontFamily="IBM Plex Mono">{e.overlap}%</text>
                        </g>
                      );
                    })}
                    {/* Nodes */}
                    {activeNetNodes.map((n,i)=>{
                      const subjectId = isMedicaid ? 'bright' : 'aps';
                      const isSubject = n.id===subjectId;
                      const lines = n.label.split('\n');
                      return (
                        <g key={i}>
                          {isSubject && (
                            <circle cx={n.x} cy={n.y} r={n.r+8} fill="none"
                              stroke={n.color} strokeWidth={1} opacity={0.25} strokeDasharray="4 3"/>
                          )}
                          <circle cx={n.x} cy={n.y} r={n.r}
                            fill={`${n.color}18`} stroke={n.color} strokeWidth={isSubject?2:1.5}/>
                          {lines.map((ln,li)=>(
                            <text key={li} x={n.x} y={n.y + (lines.length===2 ? (li===0?-4:7) : 4)}
                              textAnchor="middle" fill={C.text}
                              fontSize={isSubject ? 8 : 7} fontWeight={isSubject?600:400}
                              fontFamily="IBM Plex Sans">{ln}</text>
                          ))}
                          {/* Risk badge */}
                          <rect x={n.x+n.r-6} y={n.y-n.r-12} width={26} height={12} rx={3}
                            fill={`${n.color}22`} stroke={`${n.color}60`} strokeWidth={0.8}/>
                          <text x={n.x+n.r+7} y={n.y-n.r-3} textAnchor="middle"
                            fill={n.color} fontSize={7.5} fontFamily="IBM Plex Mono" fontWeight={600}>{n.risk}</text>
                          {/* Status dot */}
                          <circle cx={n.x-n.r+5} cy={n.y-n.r+5} r={3.5}
                            fill={n.status==='SUBJECT'?C.red:C.amber} opacity={0.9}/>
                        </g>
                      );
                    })}
                    {/* Legend */}
                    <g>
                      <circle cx={18} cy={257} r={5} fill={`${C.red}20`} stroke={C.red} strokeWidth={1.5}/>
                      <text x={26} y={261} fill={C.dim} fontSize={8} fontFamily="IBM Plex Sans">Subject</text>
                      <circle cx={75} cy={257} r={5} fill={`${C.amber}20`} stroke={C.amber} strokeWidth={1.5}/>
                      <text x={83} y={261} fill={C.dim} fontSize={8} fontFamily="IBM Plex Sans">Flagged</text>
                      <text x={138} y={261} fill={C.muted} fontSize={8} fontFamily="IBM Plex Mono">── edge label = shared patient %</text>
                    </g>
                  </svg>
                </div>
              </div>
              {/* Co-billing table */}
              <div style={{ flex:1, display:'flex', flexDirection:'column', gap:10 }}>
                <div style={{ fontSize:11, color:C.muted, marginBottom:0, ...mono }}>{isMedicaid ? 'RING-LINKED DENTAL ENTITIES · SHARED ATTRIBUTE & PATIENT ANALYSIS' : 'CONNECTED FLAGGED PROVIDERS · SHARED PATIENT ANALYSIS'}</div>
                <div style={{ background:C.s3, border:`1px solid ${C.b0}`, borderRadius:10, overflow:'hidden', flex:1 }}>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 60px 55px 60px 80px',
                    padding:'8px 12px', borderBottom:`1px solid ${C.b0}`,
                    ...mono, fontSize:9, color:C.muted, letterSpacing:'0.06em', background:C.s1 }}>
                    <span>PROVIDER</span><span>OVERLAP</span><span>VOL</span><span>RISK</span><span>STATUS</span>
                  </div>
                  {activeNetTable.map((r,i)=>(
                    <div key={i} style={{ display:'grid', gridTemplateColumns:'1fr 60px 55px 60px 80px',
                      padding:'11px 12px', borderBottom: i<netTable.length-1 ? `1px solid ${C.b0}` : 'none',
                      alignItems:'center' }}>
                      <div>
                        <div style={{ fontSize:12, fontWeight:500, color:C.text }}>{r.name}</div>
                        <div style={{ fontSize:9, color:C.muted, marginTop:2, ...mono }}>{r.spec}</div>
                      </div>
                      <div>
                        <div style={{ ...oxan, fontSize:14, fontWeight:700, color: r.overlap>=30 ? C.red : C.amber }}>{r.overlap}%</div>
                        <div style={{ height:3, background:C.b0, borderRadius:2, marginTop:4, overflow:'hidden' }}>
                          <div style={{ width:`${r.overlap*2.5}%`, height:'100%', background: r.overlap>=30 ? C.red : C.amber, borderRadius:2 }}/>
                        </div>
                      </div>
                      <span style={{ ...mono, fontSize:11, color:C.dim }}>{r.vol} pts</span>
                      <RiskBadge score={r.risk}/>
                      <span style={{ padding:'3px 7px', borderRadius:4, fontSize:9, ...mono,
                        background:`${C.amber}12`, border:`1px solid ${C.amber}30`, color:C.amber }}>
                        {r.status}
                      </span>
                    </div>
                  ))}
                </div>
                {/* AI insight */}
                <div style={{ padding:'11px 14px', background:`${C.purple}08`, border:`1px solid ${C.purple}22`, borderRadius:8, display:'flex', gap:9 }}>
                  <Bot size={13} color={C.purple} style={{ flexShrink:0, marginTop:2 }}/>
                  <div style={{ fontSize:11, color:C.dim, lineHeight:1.65 }}>
                    All {activeNetTable.length} connected {isMedicaid ? 'dental entities are flagged or have prior enforcement history' : 'providers are independently flagged'}. Combined shared-patient volume of{' '}
                    <span style={{ color:C.text, fontWeight:500 }}>{isMedicaid ? '882' : '636'} beneficiaries</span>.{' '}
                    {isMedicaid
                      ? <><span style={{ color:C.purple, fontWeight:500 }}>ProSmile Dental Lab</span> was previously terminated from GA Medicaid enrollment — SSA §1902(a)(39) applies. In-house lab relationship creates self-referral risk for prosthetic devices.</>
                      : <>Referral density is <span style={{ color:C.purple, fontWeight:500 }}>4.2× expected</span> for unaffiliated practices — consistent with a coordinated billing arrangement.</>
                    }
                  </div>
                </div>
              </div>
            </div>
            {/* Component-level feedback for Signal 3 */}
            <div style={{ padding:'0 20px 16px 20px' }}>
              <ComponentFeedback section="network_cobilling" label={isMedicaid ? 'Provider Ring / Self-Referral Signal' : 'Network Co-billing Signal'} />
            </div>
          </div>

        </div>
      )}

      {tab === 'policy' && (
        <div style={{ display:'flex', flexDirection:'column', gap:16 }} className="fu">

          {/* PKG header banner */}
          <div style={{ padding:'14px 20px', background:`${C.green}07`, border:`1px solid ${C.green}20`, borderRadius:12, display:'flex', gap:14, alignItems:'center' }}>
            <div style={{ padding:10, borderRadius:10, background:`${C.green}15`, flexShrink:0 }}>
              <GitBranch size={20} color={C.green}/>
            </div>
            <div style={{ flex:1 }}>
              <div style={{ display:'flex', alignItems:'center', gap:9, marginBottom:4 }}>
                <span style={{ ...oxan, fontSize:14, fontWeight:700, color:C.text }}>Policy Knowledge Graph — Active Analysis</span>
                <span style={{ padding:'2px 8px', borderRadius:4, background:`${C.green}18`, border:`1px solid ${C.green}40`, fontSize:9, color:C.green, ...mono }}>BETA</span>
              </div>
              <div style={{ fontSize:12, color:C.dim, lineHeight:1.6 }}>
                {activePkgSignals.length} anomaly signals queried against {isMedicaid ? 'Medicaid policy corpus (42 CFR, SSA, OIG, state Medicaid manuals)' : 'CMS policy corpus'} · <span style={{ color:C.text }}>{activePkgSignals.reduce((acc, s) => acc + s.policies.length, 0)} policy sections retrieved</span> · Grounding complete.
                Each signal below shows retrieved policy citations, AI-grounded violation determination, and recommended compliance actions.
              </div>
            </div>
            <div style={{ textAlign:'right', flexShrink:0 }}>
              <div style={{ ...mono, fontSize:9, color:C.muted, marginBottom:3 }}>POLICIES INDEXED</div>
              <div style={{ ...oxan, fontSize:22, fontWeight:800, color:C.green }}>14,382</div>
              <div style={{ ...mono, fontSize:9, color:C.muted, marginTop:1 }}>CMS docs · CFR · SSA · OIG</div>
            </div>
          </div>

          {/* Per-signal policy cards */}
          {activePkgSignals.map((sig, si) => {
            const detColor = sig.determination.startsWith('LIKELY') ? C.red : sig.determination.startsWith('POSSIBLE') ? C.amber : C.green;
            return (
              <div key={sig.id} style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, overflow:'hidden' }}>
                {/* Signal header */}
                <div style={{ padding:'13px 20px', background:`${sig.color}07`, borderBottom:`1px solid ${C.b0}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <div style={{ width:26, height:26, borderRadius:7, background:`${sig.color}20`, display:'flex', alignItems:'center', justifyContent:'center' }}>
                      <sig.icon size={13} color={sig.color}/>
                    </div>
                    <div>
                      <div style={{ ...oxan, fontWeight:700, fontSize:13, color:C.text }}>Signal {si+1} · {sig.signal}</div>
                      <div style={{ fontSize:10, color:C.dim, marginTop:1 }}>Anomaly score: <span style={{ color:sig.color, ...mono }}>{(sig.anomalyScore*100).toFixed(0)}</span> · {sig.policies.length} policy sections retrieved</div>
                    </div>
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:9 }}>
                    <div style={{ textAlign:'right' }}>
                      <div style={{ ...mono, fontSize:8, color:C.muted, marginBottom:3, letterSpacing:'0.06em' }}>AI DETERMINATION</div>
                      <div style={{ padding:'4px 11px', borderRadius:6, background:`${detColor}15`, border:`1px solid ${detColor}35`, ...oxan, fontSize:11, fontWeight:700, color:detColor }}>
                        {sig.determination}
                      </div>
                    </div>
                    <div style={{ textAlign:'center', background:C.s3, border:`1px solid ${C.b0}`, borderRadius:8, padding:'6px 12px' }}>
                      <div style={{ ...oxan, fontSize:19, fontWeight:800, color:detColor }}>{sig.determinationConf}%</div>
                      <div style={{ ...mono, fontSize:8, color:C.muted }}>CONFIDENCE</div>
                    </div>
                  </div>
                </div>

                <div style={{ padding:18, display:'flex', gap:16 }}>
                  {/* Left: retrieved policies */}
                  <div style={{ flex:1.1 }}>
                    <div style={{ ...mono, fontSize:9, color:C.muted, letterSpacing:'0.07em', marginBottom:11 }}>RETRIEVED POLICY CITATIONS · RANKED BY RELEVANCE</div>
                    <div style={{ display:'flex', flexDirection:'column', gap:9 }}>
                      {sig.policies.map((pol, pi) => (
                        <div key={pol.id} style={{ background:C.s3, border:`1px solid ${C.b0}`, borderRadius:9, padding:'12px 14px' }}>
                          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:7 }}>
                            <div style={{ flex:1 }}>
                              <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
                                <BookOpen size={11} color={C.green}/>
                                <span style={{ ...mono, fontSize:9, color:C.green }}>{pol.source}</span>
                                <span style={{ padding:'1px 6px', borderRadius:3, background:`${C.b1}`, fontSize:8, color:C.muted, ...mono }}>{pol.ruleType}</span>
                              </div>
                              <div style={{ fontSize:12, fontWeight:500, color:C.text, lineHeight:1.4 }}>{pol.title}</div>
                            </div>
                            {/* Relevance ring */}
                            <div style={{ flexShrink:0, textAlign:'center', marginLeft:12 }}>
                              <div style={{ position:'relative', width:36, height:36 }}>
                                <svg viewBox="0 0 36 36" style={{ transform:'rotate(-90deg)', width:36, height:36 }}>
                                  <circle cx="18" cy="18" r="14" fill="none" stroke={C.b0} strokeWidth="3"/>
                                  <circle cx="18" cy="18" r="14" fill="none" stroke={C.green} strokeWidth="3"
                                    strokeDasharray={`${pol.relevance * 0.879} 87.9`} strokeLinecap="round" opacity={0.8}/>
                                </svg>
                                <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center', ...mono, fontSize:9, color:C.green, fontWeight:600 }}>
                                  {pol.relevance}
                                </div>
                              </div>
                              <div style={{ ...mono, fontSize:7, color:C.muted, marginTop:2 }}>REL%</div>
                            </div>
                          </div>
                          {/* Policy snippet */}
                          <div style={{ fontSize:11, color:C.dim, lineHeight:1.65, borderLeft:`2px solid ${C.green}40`, paddingLeft:10, fontStyle:'italic' }}>
                            "{pol.snippet.length > 200 ? pol.snippet.slice(0,200)+'…' : pol.snippet}"
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Right: determination + actions */}
                  <div style={{ flex:0.9, display:'flex', flexDirection:'column', gap:11 }}>
                    {/* Reasoning chain */}
                    <div style={{ background:`${detColor}07`, border:`1px solid ${detColor}20`, borderRadius:9, padding:'12px 14px' }}>
                      <div style={{ display:'flex', alignItems:'center', gap:7, marginBottom:9 }}>
                        <Scale size={12} color={detColor}/>
                        <span style={{ ...mono, fontSize:9, color:detColor, letterSpacing:'0.07em' }}>AI REASONING CHAIN</span>
                      </div>
                      <div style={{ fontSize:11, color:C.dim, lineHeight:1.7 }}>
                        {sig.reasoning}
                      </div>
                      {/* Chain visual */}
                      <div style={{ display:'flex', alignItems:'center', gap:6, marginTop:11, flexWrap:'wrap' }}>
                        {['Anomaly Signal', 'Policy Match', 'Peer Context', 'Determination'].map((step, i, arr) => (
                          <div key={i} style={{ display:'flex', alignItems:'center', gap:5 }}>
                            <div style={{ padding:'3px 8px', borderRadius:4, background:`${detColor}15`, border:`1px solid ${detColor}30`, fontSize:9, color:detColor, ...mono }}>{step}</div>
                            {i < arr.length-1 && <ArrowRight size={9} color={C.muted}/>}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Compliance actions */}
                    <div>
                      <div style={{ ...mono, fontSize:9, color:C.muted, letterSpacing:'0.07em', marginBottom:9 }}>RECOMMENDED COMPLIANCE ACTIONS</div>
                      <div style={{ display:'flex', flexDirection:'column', gap:7 }}>
                        {sig.actions.map((act, ai) => {
                          const ac2 = act.priority==='high' ? C.red : act.priority==='med' ? C.amber : C.cyan;
                          return (
                            <div key={ai} style={{ background:C.s3, border:`1px solid ${C.b0}`, borderRadius:8, padding:'10px 12px', display:'flex', gap:10, alignItems:'flex-start' }}>
                              <div style={{ padding:'3px 7px', borderRadius:4, background:`${ac2}15`, border:`1px solid ${ac2}30`, ...mono, fontSize:8, color:ac2, whiteSpace:'nowrap', marginTop:1 }}>
                                {act.type}
                              </div>
                              <div>
                                <div style={{ fontSize:12, fontWeight:600, color:C.text, marginBottom:3 }}>{act.label}</div>
                                <div style={{ fontSize:11, color:C.dim, lineHeight:1.5 }}>{act.desc}</div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Policy gap callout */}
                    <div style={{ padding:'10px 13px', background:`${C.amber}07`, border:`1px solid ${C.amber}20`, borderRadius:8, display:'flex', gap:8, alignItems:'flex-start' }}>
                      <AlertCircle size={13} color={C.amber} style={{ flexShrink:0, marginTop:2 }}/>
                      <div>
                        <div style={{ ...mono, fontSize:8, color:C.amber, letterSpacing:'0.07em', marginBottom:4 }}>POLICY GAP IDENTIFIED</div>
                        <div style={{ fontSize:11, color:C.dim, lineHeight:1.6 }}>{sig.policyGap}</div>
                      </div>
                    </div>
                  </div>
                </div>
                
                {/* Component-level feedback for Policy Signal */}
                <div style={{ padding:'0 20px 16px 20px' }}>
                  <ComponentFeedback section={`policy_${sig.id}`} label={`${sig.signal} Policy Analysis`} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {tab === 'evidence' && (
        <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:24 }} className="fu">
          <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text, marginBottom:20 }}>Evidence & Audit Log</div>
          <div style={{ display:'flex', flexDirection:'column' }}>
            {activeEvLog.map((ev, i) => {
              const iconColor = ev.sev==='high' ? C.red : ev.sev==='med' ? C.amber : C.cyan;
              const Icon = ev.icon==='bot' ? Bot : ev.icon==='chart' ? TrendingUp : ev.icon==='network' ? Share2 : ev.icon==='file' ? FileText : ev.icon==='building' ? Building : ev.icon==='alert' ? AlertCircle : User;
              return (
                <div key={i} style={{ display:'flex', gap:16, paddingBottom: i<evLog.length-1 ? 22 : 0 }}>
                  <div style={{ display:'flex', flexDirection:'column', alignItems:'center' }}>
                    <div style={{
                      width:32, height:32, borderRadius:'50%', flexShrink:0,
                      background:`${iconColor}15`, border:`1px solid ${iconColor}35`,
                      display:'flex', alignItems:'center', justifyContent:'center',
                    }}>
                      <Icon size={14} color={iconColor} />
                    </div>
                    {i < activeEvLog.length-1 && <div style={{ width:1, flex:1, background:C.b1, marginTop:4 }} />}
                  </div>
                  <div style={{ flex:1, paddingTop:4, paddingBottom: i<evLog.length-1 ? 0 : 0 }}>
                    <div style={{ display:'flex', justifyContent:'space-between', marginBottom:5 }}>
                      <div style={{ fontSize:13, fontWeight:600, color:C.text }}>{ev.type}</div>
                      <div style={{ ...mono, fontSize:10, color:C.muted }}>{ev.date}</div>
                    </div>
                    <div style={{ fontSize:13, color:C.dim, lineHeight:1.65 }}>{ev.text}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {tab === 'timeline' && (
        <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:22 }} className="fu">
          <div style={{ ...oxan, fontWeight:700, fontSize:14, color:C.text, marginBottom:4 }}>Monthly Billing Timeline</div>
          <div style={{ fontSize:11, color:C.dim, marginBottom:18 }}>Total billing vs. at-risk billing ($K) · Total at-risk amount: <span style={{ color:C.red, fontWeight:600 }}>{isMedicaid ? '$3.4M' : '$2.1M'}</span> over 18 months</div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={activeHcpcs} margin={{ top:5, right:20, bottom:5, left:-10 }}>
              <defs>
                <linearGradient id="gBill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.amber} stopOpacity={0.3}/>
                  <stop offset="95%" stopColor={C.amber} stopOpacity={0.02}/>
                </linearGradient>
                <linearGradient id="gAtRisk" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.red} stopOpacity={0.4}/>
                  <stop offset="95%" stopColor={C.red} stopOpacity={0.02}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={C.b0} />
              <XAxis dataKey="m" tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} interval={2} />
              <YAxis tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} tickFormatter={v=>`$${v}K`} />
              <Tooltip {...tipStyle} formatter={(v,name)=>[`$${v}K`,name]} />
              <Area type="monotone" dataKey="bill" stroke={C.amber} strokeWidth={2} fill="url(#gBill)" name="Total Billing" opacity={0.7}/>
              <Area type="monotone" dataKey="atRisk" stroke={C.red} strokeWidth={2.5} fill="url(#gAtRisk)" name="At-Risk Billing" />
            </AreaChart>
          </ResponsiveContainer>
            <div style={{ display:'flex', gap:18, marginTop:12, justifyContent:'center' }}>
            <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, color:C.dim }}>
              <div style={{ width:16, height:3, background:C.amber, borderRadius:2 }}/>
              <span>Total Billing ({isMedicaid ? '$2,375K' : '$2,315K'})</span>
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, color:C.dim }}>
              <div style={{ width:16, height:3, background:C.red, borderRadius:2 }}/>
              <span>At-Risk Billing ({isMedicaid ? '$3,402K' : '$2,099K'})</span>
            </div>
          </div>
        </div>
      )}

      {/* Investigator Judgement - Final Ruling - Bottom of Page */}
      <OverallFeedback />
    </div>
  );
}

// ── POLICY INTELLIGENCE (CMS Leadership) ─────────────────────────────────────
function PolicyIntel({ prog }) {
  const [selGap, setSelGap] = useState(null);
  const ac = programs[prog].color;
  const sevColor = s => s==='CRITICAL' ? C.red : s==='HIGH' ? C.amber : s==='MEDIUM' ? C.cyan : C.green;
  const progColor = p => p==='medicare' ? C.cyan : p==='medicaid' ? C.purple : C.dim;
  const progLabel = p => p==='medicare' ? 'Medicare' : p==='medicaid' ? 'Medicaid' : 'Both Programs';

  const totExposure = prog === 'medicaid' ? '$211M' : '$323M';
  const allGaps = prog === 'medicaid' ? medicaidPolicyGaps : policyGaps;
  const filteredGaps = allGaps.filter(g => prog==='medicare' ? g.programImpact!=='medicaid' : prog==='medicaid' ? g.programImpact!=='medicare' : true);

  return (
    <div style={{ padding:24, display:'flex', flexDirection:'column', gap:18 }}>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div>
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:5 }}>
            <div style={{ padding:8, borderRadius:9, background:`${C.green}15` }}><Landmark size={18} color={C.green}/></div>
            <div style={{ ...oxan, fontSize:18, fontWeight:700, color:C.text }}>Policy Intelligence</div>
            <span style={{ padding:'2px 9px', borderRadius:5, background:`${C.green}15`, border:`1px solid ${C.green}35`, fontSize:9, ...mono, color:C.green }}>EXECUTIVE VIEW</span>
          </div>
          <div style={{ fontSize:12, color:C.dim, marginLeft:46 }}>
            AI-identified gaps, ambiguities, and recommended changes in CMS policy and oversight — derived from pattern analysis across all flagged cases.
          </div>
        </div>
        <button style={{ padding:'8px 14px', borderRadius:8, border:`1px solid ${C.b1}`, background:'transparent', color:C.dim, fontSize:12, cursor:'pointer', display:'flex', alignItems:'center', gap:6 }}>
          <Download size={12}/> Export Policy Brief
        </button>
      </div>

      {/* KPIs */}
      <div style={{ display:'flex', gap:13 }} className="fu">
        {[
          { icon:AlertCircle, label:'Policy Gaps Identified', value: String(filteredGaps.length), sub:'Across CMS, CFR, SSA, OIG corpus', color:C.red },
          { icon:DollarSign, label:'Total Estimated Exposure', value:totExposure, sub:'Attributable to policy gaps', color:C.amber },
          { icon:TriangleAlert, label:'Cases Exposing Gaps', value: prog === 'medicaid' ? '71' : '91', sub:'Q4 2024 YTD', color:C.amber },
          { icon:Lightbulb, label:'Policy Change Recs', value: String(filteredGaps.length), sub:'Actionable recommendations', color:C.green },
          { icon:Globe, label:'Programs Impacted', value: prog === 'medicaid' ? 'Medicaid' : 'Both', sub: prog === 'medicaid' ? 'State Medicaid FFS & Managed Care' : 'Medicare FFS & Medicaid FFS', color:C.purple },
        ].map((k,i) => (
          <div key={i} style={{ flex:1, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:11, padding:'16px 18px', position:'relative', overflow:'hidden' }}>
            <div style={{ position:'absolute', top:0, left:0, right:0, height:2, background:`linear-gradient(90deg, transparent, ${k.color}70, transparent)` }}/>
            <div style={{ padding:7, borderRadius:7, background:`${k.color}12`, width:'fit-content', marginBottom:11 }}>
              <k.icon size={15} color={k.color}/>
            </div>
            <div style={{ ...oxan, fontSize:22, fontWeight:800, color:k.color, lineHeight:1 }}>{k.value}</div>
            <div style={{ fontSize:11, color:C.dim, marginTop:5 }}>{k.label}</div>
            <div style={{ fontSize:10, color:C.muted, marginTop:2 }}>{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Trend + gap list */}
      <div style={{ display:'flex', gap:14 }}>
        {/* Exposure trend chart */}
        <div style={{ flex:1, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:20 }} className="fu">
          <div style={{ ...oxan, fontWeight:700, fontSize:13, color:C.text, marginBottom:3 }}>Policy Gap Exposure Trend</div>
          <div style={{ fontSize:11, color:C.dim, marginBottom:16 }}>Cases exploiting identified gaps · estimated exposure ($M) · quarterly</div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={policyTrends} margin={{ top:5, right:10, bottom:0, left:-15 }}>
              <defs>
                <linearGradient id="gGap" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.amber} stopOpacity={0.4}/>
                  <stop offset="95%" stopColor={C.amber} stopOpacity={0.02}/>
                </linearGradient>
                <linearGradient id="gExp" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.red} stopOpacity={0.3}/>
                  <stop offset="95%" stopColor={C.red} stopOpacity={0.02}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={C.b0}/>
              <XAxis dataKey="m" tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false}/>
              <YAxis tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false}/>
              <Tooltip {...tipStyle}/>
              <Area type="monotone" dataKey="cases" stroke={C.amber} strokeWidth={2} fill="url(#gGap)" name="Cases Exploiting Gaps"/>
              <Area type="monotone" dataKey="exposure" stroke={C.red} strokeWidth={2} fill="url(#gExp)" name="Exposure ($M)"/>
            </AreaChart>
          </ResponsiveContainer>
          <div style={{ display:'flex', gap:16, marginTop:8 }}>
            {[{c:C.amber,l:'Cases exploiting gaps'},{c:C.red,l:'Estimated exposure ($M)'}].map((x,i)=>(
              <div key={i} style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:C.dim }}>
                <div style={{ width:12, height:2, background:x.c }}/>{x.l}
              </div>
            ))}
          </div>
        </div>

        {/* Gap severity matrix */}
        <div style={{ flex:1, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, padding:20 }} className="fu">
          <div style={{ ...oxan, fontWeight:700, fontSize:13, color:C.text, marginBottom:3 }}>Gap Severity vs. Exposure</div>
          <div style={{ fontSize:11, color:C.dim, marginBottom:14 }}>Each bubble = one policy gap · size = estimated $ exposure</div>
          <svg viewBox="0 0 320 190" width="100%" style={{ display:'block' }}>
            {/* Axes */}
            <line x1="40" y1="10" x2="40" y2="160" stroke={C.b0} strokeWidth={1}/>
            <line x1="40" y1="160" x2="310" y2="160" stroke={C.b0} strokeWidth={1}/>
            <text x="175" y="185" textAnchor="middle" fill={C.muted} fontSize={9} fontFamily="IBM Plex Mono">CASES EXPOSING GAP →</text>
            <text x="14" y="90" textAnchor="middle" fill={C.muted} fontSize={9} fontFamily="IBM Plex Mono" transform="rotate(-90, 14, 90)">EXPOSURE ($M) →</text>
            {/* Grid lines */}
            {[40,80,120].map(y=><line key={y} x1="40" y1={y} x2="310" y2={y} stroke={C.b0} strokeWidth={0.5} strokeDasharray="4 4"/>)}
            {[100,170,240].map(x=><line key={x} x1={x} y1="10" x2={x} y2="160" stroke={C.b0} strokeWidth={0.5} strokeDasharray="4 4"/>)}
            {/* Bubbles */}
            {(prog === 'medicaid' ? [
              {x:155,y:55,r:18,c:C.red,  l:'MG1',label:'Crown Ratio Threshold'},
              {x:215,y:80,r:14,c:C.amber,l:'MG2',label:'Technician Cert Check'},
              {x:175,y:110,r:16,c:C.amber,l:'MG3',label:'MCO Enrollment Verify'},
              {x:235,y:125,r:11,c:C.cyan, l:'MG4',label:'NCCI Edit Lag'},
            ] : [
              {x:170,y:55,r:18,c:C.red,  l:'G1',label:'Code Concentration'},
              {x:235,y:75,r:15,c:C.amber,l:'G2',label:'Outlier Threshold'},
              {x:135,y:95,r:13,c:C.amber,l:'G3',label:'AKS Threshold'},
              {x:175,y:120,r:11,c:C.cyan, l:'G4',label:'NCCI Edit Lag'},
            ]).map((b,i)=>(
              <g key={i}>
                <circle cx={b.x} cy={b.y} r={b.r} fill={`${b.c}20`} stroke={b.c} strokeWidth={1.5}/>
                <text x={b.x} y={b.y+4} textAnchor="middle" fill={b.c} fontSize={8} fontFamily="IBM Plex Mono" fontWeight={600}>{b.l}</text>
                <text x={b.x} y={b.y+b.r+11} textAnchor="middle" fill={C.muted} fontSize={7} fontFamily="IBM Plex Sans">{b.label}</text>
              </g>
            ))}
          </svg>
        </div>
      </div>

      {/* Gap detail cards */}
      <div className="fu">
        <div style={{ ...mono, fontSize:9, color:C.muted, letterSpacing:'0.07em', marginBottom:12 }}>IDENTIFIED POLICY GAPS & RECOMMENDATIONS</div>
        <div style={{ display:'flex', flexDirection:'column', gap:11 }}>
          {filteredGaps.map((gap, i) => {
            const sc = sevColor(gap.severity);
            const isOpen = selGap === gap.id;
            return (
              <div key={gap.id} style={{ background:C.s2, border:`1px solid ${isOpen ? C.b2 : C.b0}`, borderRadius:11, overflow:'hidden' }}>
                {/* Row header */}
                <div onClick={()=>setSelGap(isOpen ? null : gap.id)} style={{
                  display:'grid', gridTemplateColumns:'26px 1fr 130px 110px 100px 130px 42px',
                  padding:'13px 18px', cursor:'pointer', alignItems:'center', gap:8,
                }}>
                  <div style={{ width:8, height:8, borderRadius:'50%', background:sc, boxShadow:`0 0 6px ${sc}` }}/>
                  <div>
                    <div style={{ fontSize:13, fontWeight:500, color:C.text }}>{gap.title}</div>
                    <div style={{ ...mono, fontSize:10, color:C.muted, marginTop:2 }}>{gap.source}</div>
                  </div>
                  <div>
                    <span style={{ padding:'3px 8px', borderRadius:4, background:`${sc}12`, border:`1px solid ${sc}25`, fontSize:10, color:sc, ...mono }}>{gap.severity}</span>
                  </div>
                  <div style={{ fontSize:11, color:C.dim }}>{gap.scope}</div>
                  <div style={{ ...oxan, fontSize:13, fontWeight:700, color:C.amber }}>{gap.estimatedExposure}</div>
                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                    <div style={{ width:7, height:7, borderRadius:'50%', background:progColor(gap.programImpact) }}/>
                    <span style={{ fontSize:11, color:C.dim }}>{progLabel(gap.programImpact)}</span>
                  </div>
                  <ChevronRight size={14} color={C.muted} style={{ transform: isOpen ? 'rotate(90deg)' : 'none', transition:'transform 0.2s' }}/>
                </div>

                {/* Expanded detail */}
                {isOpen && (
                  <div style={{ borderTop:`1px solid ${C.b0}`, padding:'16px 20px', background:C.s3, display:'flex', gap:18 }} className="fu">
                    <div style={{ flex:1 }}>
                      <div style={{ ...mono, fontSize:9, color:C.muted, letterSpacing:'0.07em', marginBottom:9 }}>POLICY GAP DESCRIPTION</div>
                      <div style={{ fontSize:12, color:C.dim, lineHeight:1.7, marginBottom:14 }}>{gap.description}</div>
                      <div style={{ display:'flex', gap:10 }}>
                        {[
                          {l:'Affected Providers',v:gap.affectedProviders.toLocaleString(),c:C.amber},
                          {l:'Cases Exposing This Gap',v:gap.casesExposing,c:C.red},
                          {l:'Est. Total Exposure',v:gap.estimatedExposure,c:C.amber},
                        ].map((s,j)=>(
                          <div key={j} style={{ flex:1, background:C.s2, border:`1px solid ${C.b0}`, borderRadius:8, padding:'10px 12px' }}>
                            <div style={{ ...oxan, fontSize:18, fontWeight:800, color:s.c }}>{s.v}</div>
                            <div style={{ fontSize:10, color:C.muted, marginTop:3 }}>{s.l}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div style={{ flex:1 }}>
                      <div style={{ ...mono, fontSize:9, color:C.green, letterSpacing:'0.07em', marginBottom:9 }}>RECOMMENDED POLICY CHANGE</div>
                      <div style={{ padding:'13px 15px', background:`${C.green}07`, border:`1px solid ${C.green}20`, borderRadius:9, marginBottom:11 }}>
                        <div style={{ display:'flex', gap:8, alignItems:'flex-start' }}>
                          <Lightbulb size={13} color={C.green} style={{ flexShrink:0, marginTop:2 }}/>
                          <div style={{ fontSize:12, color:C.dim, lineHeight:1.7 }}>{gap.recommendation}</div>
                        </div>
                      </div>
                      <div style={{ display:'flex', gap:8 }}>
                        <button style={{ flex:1, padding:'8px 0', borderRadius:7, border:`1px solid ${C.green}40`, background:`${C.green}10`, color:C.green, fontSize:11, cursor:'pointer', ...oxan, fontWeight:600 }}>
                          Add to Policy Brief
                        </button>
                        <button style={{ flex:1, padding:'8px 0', borderRadius:7, border:`1px solid ${C.b1}`, background:'transparent', color:C.dim, fontSize:11, cursor:'pointer' }}>
                          View Affected Cases
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── CASE MANAGEMENT ───────────────────────────────────────────────────────────
function CaseMgmt({ prog = 'medicare', feedback = {}, onFeedback = () => {} }) {
  const activeCases = prog === 'medicaid' ? medicaidCases : cases;
  const sc = { 'Under Review':C.cyan, 'Escalated':C.red, 'Pending':C.amber, 'Closed · Confirmed':C.green, 'Closed · Cleared':C.muted };
  const summary = prog === 'medicaid' ? [
    {l:'Pending',n:2,c:C.amber},{l:'Under Review',n:3,c:C.cyan},
    {l:'Escalated',n:1,c:C.red},{l:'Confirmed',n:1,c:C.green},{l:'Cleared',n:1,c:C.muted},
  ] : [
    {l:'Pending',n:2,c:C.amber},{l:'Under Review',n:3,c:C.cyan},
    {l:'Escalated',n:1,c:C.red},{l:'Confirmed',n:1,c:C.green},{l:'Cleared',n:1,c:C.muted},
  ];
  
  // Helper to get latest feedback for case
  const getLatestFeedback = (npi) => {
    if (!feedback[npi] || !feedback[npi].overall) return null;
    return feedback[npi].overall[0];
  };
  
  // Helper to determine suggested action based on feedback
  const getSuggestedAction = (caseItem) => {
    // Handle closed cases first
    if (caseItem.status === 'Closed · Cleared') {
      return { action: '—', color: C.muted, icon: null };
    }
    const fb = getLatestFeedback(caseItem.npi);
    if (!fb) return { action: 'Review Needed', color: C.amber, icon: Clock };
    if (fb.verdict === 'confirmed') return { action: 'Escalate', color: C.red, icon: ArrowUp };
    if (fb.verdict === 'legitimate') return { action: 'Close · Clear', color: C.green, icon: CheckCircle };
    if (fb.verdict === 'watch') return { action: 'Monitor', color: C.cyan, icon: AlertCircle };
    return { action: 'More Info Needed', color: C.amber, icon: AlertCircle };
  };

  return (
    <div style={{ padding:24, display:'flex', flexDirection:'column', gap:18 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div>
          <div style={{ ...oxan, fontSize:18, fontWeight:700, color:C.text }}>Case Management</div>
          <div style={{ fontSize:12, color:C.dim, marginTop:3 }}>{activeCases.length} active cases · 1 escalated · {prog === 'medicaid' ? '$11.5M' : '$6.2M'} under review</div>
        </div>
        <div style={{ display:'flex', gap:8 }}>
          <button style={{ padding:'7px 13px', borderRadius:7, border:`1px solid ${C.b1}`, background:'transparent', color:C.dim, fontSize:12, cursor:'pointer', display:'flex', alignItems:'center', gap:6 }}>
            <Filter size={12}/> Filter
          </button>
          <button style={{ padding:'7px 13px', borderRadius:7, border:`1px solid ${C.b1}`, background:'transparent', color:C.dim, fontSize:12, cursor:'pointer', display:'flex', alignItems:'center', gap:6 }}>
            <Download size={12}/> Export
          </button>
        </div>
      </div>

      <div style={{ display:'flex', gap:11 }} className="fu">
        {summary.map((s,i) => (
          <div key={i} style={{ flex:1, padding:'14px 16px', background:C.s2, border:`1px solid ${C.b0}`, borderRadius:10 }}>
            <div style={{ ...oxan, fontSize:24, fontWeight:800, color:s.c }}>{s.n}</div>
            <div style={{ fontSize:11, color:C.muted, marginTop:3 }}>{s.l}</div>
          </div>
        ))}
      </div>

      <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, overflow:'hidden' }} className="fu">
        {/* Group header row */}
        <div style={{
          display:'grid', gridTemplateColumns:'110px 240px 2px 1fr 1fr 1fr 2px 1fr 1fr 1fr',
          padding:'8px 18px 4px 18px', background:C.s3, borderBottom:`1px solid ${C.b0}50`,
        }}>
          <div style={{ gridColumn:'1 / 3' }}></div>
          <div style={{ borderLeft:`2px solid ${C.cyan}40` }}></div>
          <div style={{ gridColumn:'4 / 7', display:'flex', alignItems:'center', gap:5 }}>
            <Bot size={10} style={{ color:C.cyan }}/>
            <span style={{ ...mono, fontSize:9, color:C.cyan, letterSpacing:'0.08em' }}>AI FINDINGS</span>
          </div>
          <div style={{ borderLeft:`2px solid ${C.cyan}40` }}></div>
          <div style={{ gridColumn:'8 / 11', display:'flex', alignItems:'center', gap:5, paddingLeft:12 }}>
            <User size={10} style={{ color:C.cyan }}/>
            <span style={{ ...mono, fontSize:9, color:C.cyan, letterSpacing:'0.08em' }}>CASE MANAGEMENT WORKFLOW</span>
          </div>
        </div>
        
        {/* Column header row */}
        <div style={{
          display:'grid', gridTemplateColumns:'110px 240px 2px 1fr 1fr 1fr 2px 1fr 1fr 1fr',
          padding:'10px 18px', background:C.s3, borderBottom:`1px solid ${C.b0}`,
          ...mono, fontSize:10, color:C.muted, letterSpacing:'0.06em',
        }}>
          <span>CASE ID</span><span>PROVIDER</span>
          <div style={{ borderLeft:`2px solid ${C.cyan}40` }}></div>
          <span style={{ paddingLeft:12 }}>TYPE</span>
          <span>RISK</span>
          <span>AT RISK</span>
          <div style={{ borderLeft:`2px solid ${C.cyan}40` }}></div>
          <span style={{ paddingLeft:12 }}>STATUS</span><span>ANALYST</span><span>INVESTIGATOR ACTION</span>
        </div>
        {activeCases.map((c, i) => {
          const fb = getLatestFeedback(c.npi);
          const suggestedAction = getSuggestedAction(c);
          const ActionIcon = suggestedAction.icon;
          const riskColor = c.risk >= 90 ? C.red : c.risk >= 75 ? C.amber : C.green;
          return (
          <div key={c.id} style={{
            display:'grid', gridTemplateColumns:'110px 240px 2px 1fr 1fr 1fr 2px 1fr 1fr 1fr',
            padding:'13px 18px', alignItems:'center',
            borderBottom: i < activeCases.length-1 ? `1px solid ${C.b0}` : 'none',
            transition:'background 0.15s', cursor:'pointer',
          }}
            onMouseEnter={e=>e.currentTarget.style.background=C.s3}
            onMouseLeave={e=>e.currentTarget.style.background='transparent'}
          >
            <span style={{ ...mono, fontSize:11, color:C.cyan }}>{c.id}</span>
            <div>
              <div style={{ fontSize:13, fontWeight:500, color:C.text }}>{c.prov}</div>
              {fb && fb.comment && (
                <div style={{ fontSize:9, color:C.dim, marginTop:2, fontStyle:'italic' }}>
                  "{fb.comment.slice(0,50)}{fb.comment.length > 50 ? '...' : ''}"
                </div>
              )}
            </div>
            <div style={{ borderLeft:`2px solid ${C.cyan}40`, height:'100%' }}></div>
            <span style={{ fontSize:11, color:C.dim, paddingLeft:12 }}>{c.type}</span>
            <RiskBadge score={c.risk} />
            <span style={{ ...oxan, fontSize:12, fontWeight:700, color: c.amt==='—' ? C.muted : riskColor }}>{c.amt}</span>
            <div style={{ borderLeft:`2px solid ${C.cyan}40`, height:'100%' }}></div>
            <div style={{ paddingLeft:12 }}>
              <span style={{
                padding:'3px 8px', borderRadius:4, fontSize:10, ...mono,
                background:`${sc[c.status]}15`, border:`1px solid ${sc[c.status]}30`,
                color:sc[c.status], whiteSpace:'nowrap',
              }}>{c.status}</span>
            </div>
            <span style={{ fontSize:12, color: c.analyst==='Unassigned' ? C.amber : C.dim }}>{c.analyst}</span>
            <div>
              {c.status === 'Closed · Cleared' ? (
                <span style={{ fontSize:12, color:C.muted, ...mono }}>—</span>
              ) : fb ? (
                <div style={{ 
                  padding:'5px 10px', borderRadius:5, fontSize:10, ...mono,
                  background:`${suggestedAction.color}15`, border:`1px solid ${suggestedAction.color}40`,
                  color:suggestedAction.color, whiteSpace:'nowrap', display:'flex', alignItems:'center', gap:5
                }}>
                  <ActionIcon size={11}/> {suggestedAction.action}
                </div>
              ) : (
                <span style={{ fontSize:10, color:C.muted, ...mono }}>Pending Review</span>
              )}
            </div>
          </div>
        )})}
      </div>
    </div>
  );
}

// ── AI PANEL ──────────────────────────────────────────────────────────────────
function AIPanel({ prog = 'medicare', onClose }) {
  const isMedicaid = prog === 'medicaid';
  const activeCanned = isMedicaid ? medicaidCanned : canned;
  const initialSubject = isMedicaid ? 'Bright Smiles Dental Group (NPI: 3344556677)' : 'Advanced Pain Specialists (NPI: 1234567890)';
  const initialMessage = isMedicaid
    ? "I've analyzed Bright Smiles Dental Group (NPI: 3344556677) and identified 3 high-confidence anomaly signals:\n\n1. CDT Code Consolidation — Billed 28 unique CDT codes in Mar 2023. By Aug 2024, just 5 codes account for 97% of billing, overwhelmingly crowns (D2740/D2750). Consistent with systematic overtreatment following corporate acquisition. Crown rate is 80% vs. 14% peer median.\n\n2. High-Cost Code Upcoding — Crown and root canal procedures are 5.7× above peer median — clinically implausible for a pediatric dental practice without systematic overtreatment. Pattern initiated within 30 days of acquisition on Jul 8, 2023.\n\n3. Shared-Attribute Provider Ring — 4 linked dental entities share addresses, phone numbers, and banking information. In-house dental lab (ProSmile) was previously terminated from GA Medicaid enrollment, creating self-referral risk for prosthetic devices.\n\nEstimated overpayment risk: $3.4M (FY2024)"
    : "I've analyzed Advanced Pain Specialists (NPI: 1234567890) and identified 3 high-confidence anomaly signals:\n\n1. HCPCS Consolidation — Billed 47 unique procedure codes in Mar 2023. By Aug 2024, just 6 codes account for 98% of billing. Consistent with systematic code cherry-picking to maximize reimbursement.\n\n2. E&M Upcoding — 99215 (highest-complexity visit) is 78% of all E&M claims vs. peer median of 18%. This provider ranks in the top 1.3% nationally — statistically improbable without systematic miscoding.\n\n3. Network Co-billing — 34% of patients share treatment history with Sunrise Medical Group (also flagged). Mutual referral density is 4.2× expected for unrelated practices.\n\nEstimated overpayment risk: $2.1M (FY2024)";

  const [input, setInput] = useState('');
  const [msgs, setMsgs] = useState([{ role:'assistant', text: initialMessage }]);

  const send = () => {
    if (!input.trim()) return;
    const q = input.toLowerCase();
    setMsgs(m => [...m, { role:'user', text:input }]);
    setInput('');
    const key = q.includes('code') ? 'codes' : q.includes('compar') || q.includes('peer') ? 'compare' : q.includes('next') || q.includes('recommend') || q.includes('step') ? 'next' : 'default';
    setTimeout(() => setMsgs(m => [...m, { role:'assistant', text:activeCanned[key] }]), 600);
  };

  const prompts = isMedicaid
    ? ['What CDT codes are involved?','Compare to dental peers','Recommend next steps']
    : ['What codes are involved?','Compare to peers','Recommend next steps'];

  return (
    <div className="sr" style={{
      position:'fixed', right:0, top:0, bottom:0, width:420,
      background:C.s1, borderLeft:`1px solid ${C.b1}`,
      display:'flex', flexDirection:'column', zIndex:100,
    }}>
      {/* Header */}
      <div style={{ padding:'15px 18px', borderBottom:`1px solid ${C.b0}`, display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div style={{ padding:8, borderRadius:8, background:`${C.cyan}15` }}><Bot size={17} color={C.cyan}/></div>
          <div>
            <div style={{ ...oxan, fontSize:14, fontWeight:700, color:C.text }}>AI Investigator</div>
            <div style={{ ...mono, fontSize:10, color:C.cyan, marginTop:1 }}>● ACTIVE · {isMedicaid ? 'Bright Smiles Dental Group' : 'Advanced Pain Specialists'}</div>
          </div>
        </div>
        <button onClick={onClose} style={{ background:'none', border:'none', cursor:'pointer', color:C.muted }}><X size={17}/></button>
      </div>
      {/* Suggested prompts */}
      <div style={{ padding:'10px 16px', borderBottom:`1px solid ${C.b0}`, display:'flex', gap:7, flexWrap:'wrap' }}>
        {prompts.map(p => (
          <button key={p} onClick={()=>setInput(p)} style={{
            padding:'5px 10px', borderRadius:5, border:`1px solid ${C.b1}`,
            background:C.s2, color:C.dim, fontSize:11, cursor:'pointer',
          }}>{p}</button>
        ))}
      </div>
      {/* Messages */}
      <div style={{ flex:1, overflowY:'auto', padding:'18px 16px', display:'flex', flexDirection:'column', gap:14 }}>
        {msgs.map((msg, i) => (
          <div key={i} style={{ display:'flex', gap:9, flexDirection:msg.role==='user'?'row-reverse':'row', alignItems:'flex-start' }}>
            {msg.role==='assistant' && (
              <div style={{ width:28, height:28, borderRadius:7, background:`${C.cyan}15`, flexShrink:0, display:'flex', alignItems:'center', justifyContent:'center', marginTop:2 }}>
                <Bot size={14} color={C.cyan}/>
              </div>
            )}
            <div style={{
              maxWidth:'88%', padding:'11px 13px', borderRadius:10,
              background: msg.role==='user' ? `${C.cyan}12` : C.s2,
              border:`1px solid ${msg.role==='user' ? C.cyan+'28' : C.b0}`,
              fontSize:12, color:C.text, lineHeight:1.75, whiteSpace:'pre-wrap',
            }}>
              {msg.text}
            </div>
          </div>
        ))}
      </div>
      {/* Input */}
      <div style={{ padding:'14px 16px', borderTop:`1px solid ${C.b0}`, display:'flex', gap:9 }}>
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&send()}
          placeholder="Ask about this provider..."
          style={{ flex:1, padding:'10px 13px', borderRadius:8, border:`1px solid ${C.b0}`, background:C.s2, color:C.text, fontSize:13 }}
        />
        <button onClick={send} style={{
          padding:'10px 13px', borderRadius:8, border:`1px solid ${C.cyan}40`,
          background:`${C.cyan}15`, color:C.cyan, cursor:'pointer',
        }}><Send size={15}/></button>
      </div>
    </div>
  );
}

// ── MAIN APP ───────────────────────────────────────────────────────────────────
export default function App() {
  const [screen, setScreen] = useState('dashboard');
  const [prog, setProg] = useState('medicare');
  const [aiOpen, setAiOpen] = useState(false);
  const [selProv, setSelProv] = useState(null);
  // Feedback state: { [providerId]: { overall: [history], components: { [section]: [history] } } }
  const [feedback, setFeedback] = useState({});
  // Mock investigator info
  const investigator = { id: 'inv-001', name: 'J. Morrison' };
  const pd = programs[prog];

  const nav = [
    { id:'dashboard', icon:LayoutDashboard, label:'Dashboard' },
    { id:'feed',      icon:AlertTriangle,  label:'Anomaly Feed' },
    { id:'provider',  icon:User,           label:'Provider Deep-Dive' },
    { id:'cases',     icon:Briefcase,      label:'Case Management' },
    { id:'policy',    icon:Landmark,       label:'Policy Intelligence', badge:true },
  ];

  const handleSelect = (prov) => { setSelProv(prov); setScreen('provider'); };

  // Feedback update handler
  const handleFeedback = (providerId, section, verdict, comment) => {
    setFeedback(prev => {
      const now = new Date().toISOString();
      const entry = { verdict, comment, investigator, timestamp: now };
      const prevProv = prev[providerId] || { overall: [], components: {} };
      if (section === 'overall') {
        return {
          ...prev,
          [providerId]: {
            ...prevProv,
            overall: [entry, ...(prevProv.overall || [])],
          }
        };
      } else {
        return {
          ...prev,
          [providerId]: {
            ...prevProv,
            components: {
              ...prevProv.components,
              [section]: [entry, ...(prevProv.components?.[section] || [])],
            },
          }
        };
      }
    });
  };

  return (
    <>
      <style>{CSS}</style>
      <div style={{ display:'flex', height:'100vh', background:C.bg, overflow:'hidden', color:C.text }}>
        {/* Sidebar */}
        <div style={{ width:220, background:C.s1, borderRight:`1px solid ${C.b0}`, display:'flex', flexDirection:'column', flexShrink:0, zIndex:10 }}>
          {/* Logo */}
          <div style={{ padding:'18px 18px 14px', borderBottom:`1px solid ${C.b0}` }}>
            <div style={{ display:'flex', alignItems:'center', gap:10 }}>
              <div style={{ width:34, height:34, borderRadius:9, background:`linear-gradient(135deg, ${pd.color}, ${pd.color}60)`, display:'flex', alignItems:'center', justifyContent:'center' }}>
                <Shield size={17} color="#fff"/>
              </div>
              <div>
                <div style={{ ...oxan, fontSize:15, fontWeight:800, color:C.text, letterSpacing:'0.01em' }}>KPMG Fraud Fighter</div>
                <div style={{ fontSize:10, color:C.muted }}>Explainable AI Fraud Detection</div>
              </div>
            </div>
          </div>
          {/* Program switcher */}
          <div style={{ padding:'12px 13px', borderBottom:`1px solid ${C.b0}` }}>
            <div style={{ ...mono, fontSize:9, color:C.muted, letterSpacing:'0.08em', marginBottom:8 }}>PROGRAM</div>
            <div style={{ display:'flex', background:C.s2, borderRadius:8, padding:3, border:`1px solid ${C.b0}` }}>
              {['medicare','medicaid'].map(p => (
                <button key={p} onClick={()=>setProg(p)} style={{
                  flex:1, padding:'7px 0', borderRadius:5, border:'none',
                  background: prog===p ? programs[p].color : 'transparent',
                  color: prog===p ? '#000' : C.muted,
                  ...oxan, fontSize:9, fontWeight:800, cursor:'pointer',
                  letterSpacing:'0.05em', transition:'all 0.2s',
                }}>
                  {p === 'medicare' ? 'MEDICARE' : 'MEDICAID'}
                </button>
              ))}
            </div>
          </div>
          {/* Nav */}
          <nav style={{ padding:'10px 10px', flex:1 }}>
            {nav.map(item => (
              <button key={item.id} onClick={()=>setScreen(item.id)} style={{
                display:'flex', alignItems:'center', gap:10, width:'100%',
                padding:'10px 12px', borderRadius:8, border:'none', marginBottom:3,
                background: screen===item.id ? `${pd.color}14` : 'transparent',
                color: screen===item.id ? pd.color : C.dim,
                fontSize:13, cursor:'pointer', textAlign:'left',
                fontWeight: screen===item.id ? 500 : 400,
                borderLeft:`2px solid ${screen===item.id ? pd.color : 'transparent'}`,
              }}>
                <item.icon size={15}/>
                <span style={{ flex:1 }}>{item.label}</span>
                {item.badge && (
                  <span style={{ padding:'1px 5px', borderRadius:3, background:`${C.green}18`, border:`1px solid ${C.green}35`, fontSize:8, color:C.green, ...mono }}>BETA</span>
                )}
              </button>
            ))}
          </nav>
          {/* AI Toggle */}
          <div style={{ padding:'10px 10px', borderTop:`1px solid ${C.b0}` }}>
            <button onClick={()=>setAiOpen(!aiOpen)} style={{
              display:'flex', alignItems:'center', gap:10, width:'100%',
              padding:'10px 12px', borderRadius:8,
              border:`1px solid ${aiOpen ? C.cyan+'50' : C.b0}`,
              background: aiOpen ? `${C.cyan}12` : C.s2,
              color: aiOpen ? C.cyan : C.dim,
              fontSize:13, cursor:'pointer',
            }}>
              <Bot size={15}/>AI Investigator
              {aiOpen && <div style={{ marginLeft:'auto', width:7, height:7, borderRadius:'50%', background:C.cyan, boxShadow:`0 0 8px ${C.cyan}`, animation:'pulseRing 2s infinite' }}/>} 
            </button>
          </div>
        </div>

        {/* Main */}
        <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden', transition:'margin-right 0.35s cubic-bezier(.16,1,.3,1)', marginRight: aiOpen ? 420 : 0 }}>
          {/* Top bar */}
          <div style={{ height:54, background:C.s1, borderBottom:`1px solid ${C.b0}`, display:'flex', alignItems:'center', padding:'0 22px', gap:14, flexShrink:0 }}>
            <div style={{ position:'relative' }}>
              <Search size={13} color={C.muted} style={{ position:'absolute', left:11, top:'50%', transform:'translateY(-50%)' }}/>
              <input placeholder="Search providers, NPIs, cases..." style={{
                padding:'7px 11px 7px 32px', borderRadius:7, border:`1px solid ${C.b0}`,
                background:C.s2, color:C.text, fontSize:13, width:300,
              }}/>
            </div>
            <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:10 }}>
              <div style={{ padding:'4px 10px', borderRadius:6, background:`${pd.color}12`, border:`1px solid ${pd.color}28`, ...mono, fontSize:10, color:pd.color }}>
                {prog === 'medicaid' ? 'Medicaid Program Integrity' : pd.label}
              </div>
              <button style={{ padding:8, borderRadius:7, background:C.s2, border:`1px solid ${C.b0}`, color:C.dim, cursor:'pointer', position:'relative' }}>
                <Bell size={14}/>
                <div style={{ position:'absolute', top:7, right:7, width:5, height:5, borderRadius:'50%', background:C.red }}/>
              </button>
              <div style={{ width:32, height:32, borderRadius:'50%', background:`${pd.color}18`, border:`1px solid ${pd.color}35`, display:'flex', alignItems:'center', justifyContent:'center', ...oxan, fontSize:12, fontWeight:700, color:pd.color }}>
                JM
              </div>
            </div>
          </div>
          {/* Content */}
          <div style={{ flex:1, overflowY:'auto' }}>
            {screen==='dashboard' && <Dashboard prog={prog}/>}
            {screen==='feed'      && <AnomalyFeed prog={prog} onSelect={handleSelect} feedback={feedback} onFeedback={handleFeedback}/>}
            {screen==='provider'  && <ProviderDive provider={selProv} prog={prog} feedback={feedback} onFeedback={handleFeedback}/>}
            {screen==='cases'     && <CaseMgmt prog={prog} feedback={feedback} onFeedback={handleFeedback}/>}
            {screen==='policy'    && <PolicyIntel prog={prog}/>}
          </div>
        </div>

        {aiOpen && <AIPanel prog={prog} onClose={()=>setAiOpen(false)}/>}
      </div>
    </>
  );
}
