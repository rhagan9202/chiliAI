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
    label: 'Medicaid FFS', color: C.purple,
    kpis: { flagged:'2,108', savings:'$31.4M', resolved:'1,203', confidence:'85%' },
    trend: [
      {m:'Sep',a:120,s:2.1},{m:'Oct',a:148,s:2.5},{m:'Nov',a:137,s:2.3},{m:'Dec',a:162,s:2.8},
      {m:'Jan',a:198,s:3.4},{m:'Feb',a:221,s:3.9},{m:'Mar',a:208,s:3.6},{m:'Apr',a:239,s:4.1},
      {m:'May',a:261,s:4.7},{m:'Jun',a:283,s:5.0},{m:'Jul',a:265,s:4.6},{m:'Aug',a:302,s:5.4},
    ],
    cats: [{n:'Billing Pattern',v:12.8,c:782},{n:'Network Anomaly',v:9.4,c:534},{n:'Trend Shift',v:5.7,c:389},{n:'Beneficiary Abuse',v:3.5,c:403}],
  },
};

const feed = [
  {id:1,name:'Advanced Pain Specialists',npi:'1234567890',type:'Billing + Trend',risk:94,conf:89,amt:'$2.1M',flag:'UPCODING · HCPCS CONSOLIDATION',days:2,city:'Miami, FL',spec:'Pain Management'},
  {id:2,name:'Sunrise Medical Group',npi:'9876543210',type:'Network',risk:91,conf:86,amt:'$1.8M',flag:'REFERRAL RING DETECTED',days:3,city:'Houston, TX',spec:'Primary Care'},
  {id:3,name:'Dr. James Kellerman',npi:'1122334455',type:'Billing',risk:89,conf:92,amt:'$847K',flag:'E&M UPCODING · TOP 2% PEERS',days:1,city:'Chicago, IL',spec:'Internal Medicine'},
  {id:4,name:'Gulf Coast DME Supply',npi:'5544332211',type:'Billing',risk:87,conf:84,amt:'$1.2M',flag:'PHANTOM BILLING INDICATORS',days:5,city:'New Orleans, LA',spec:'DME Supplier'},
  {id:5,name:'Premier Diagnostics LLC',npi:'6677889900',type:'Network + Billing',risk:83,conf:81,amt:'$980K',flag:'SELF-REFERRAL · OVER-ORDERING',days:4,city:'Phoenix, AZ',spec:'Diagnostics'},
  {id:6,name:'Dr. Maria Santos',npi:'0099887766',type:'Trend',risk:79,conf:78,amt:'$634K',flag:'SPECIALTY SHIFT ANOMALY',days:7,city:'Los Angeles, CA',spec:'Family Medicine'},
  {id:7,name:'Coastal Rehab Center',npi:'1357924680',type:'Network',risk:74,conf:76,amt:'$1.4M',flag:'KICKBACK INDICATORS',days:6,city:'Tampa, FL',spec:'Rehabilitation'},
  {id:8,name:'Dr. Robert Chen',npi:'2468013579',type:'Billing',risk:71,conf:83,amt:'$512K',flag:'MODIFIER ABUSE · 59 MODIFIER',days:8,city:'Seattle, WA',spec:'Surgery'},
];

const hcpcs = [
  {m:"Mar'23",codes:47,top3:38,bill:42},{m:"Apr'23",codes:44,top3:41,bill:45},
  {m:"May'23",codes:41,top3:45,bill:49},{m:"Jun'23",codes:38,top3:49,bill:54},
  {m:"Jul'23",codes:33,top3:54,bill:61},{m:"Aug'23",codes:29,top3:60,bill:71},
  {m:"Sep'23",codes:24,top3:67,bill:84},{m:"Oct'23",codes:19,top3:74,bill:98},
  {m:"Nov'23",codes:15,top3:81,bill:115},{m:"Dec'23",codes:12,top3:86,bill:132},
  {m:"Jan'24",codes:9,top3:91,bill:158},{m:"Feb'24",codes:7,top3:94,bill:174},
  {m:"Mar'24",codes:6,top3:96,bill:189},{m:"Apr'24",codes:6,top3:97,bill:201},
  {m:"May'24",codes:6,top3:97,bill:210},{m:"Jun'24",codes:6,top3:98,bill:218},
  {m:"Jul'24",codes:6,top3:98,bill:221},{m:"Aug'24",codes:6,top3:98,bill:228},
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
  {m:"Mar'23",prov:31,peer:19},{m:"Apr'23",prov:34,peer:19},{m:"May'23",prov:37,peer:18},
  {m:"Jun'23",prov:41,peer:19},{m:"Jul'23",prov:45,peer:20},{m:"Aug'23",prov:51,peer:19},
  {m:"Sep'23",prov:58,peer:18},{m:"Oct'23",prov:63,peer:19},{m:"Nov'23",prov:67,peer:20},
  {m:"Dec'23",prov:70,peer:19},{m:"Jan'24",prov:72,peer:18},{m:"Feb'24",prov:74,peer:19},
  {m:"Mar'24",prov:75,peer:18},{m:"Apr'24",prov:76,peer:19},{m:"May'24",prov:77,peer:19},
  {m:"Jun'24",prov:77,peer:18},{m:"Jul'24",prov:78,peer:19},{m:"Aug'24",prov:78,peer:18},
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
  {date:'Aug 28, 2024',type:'AI Detection',icon:'bot',text:'Automated model flagged HCPCS consolidation pattern — 47 → 6 unique codes over 18 months with 98% billing concentration.',sev:'high'},
  {date:'Aug 29, 2024',type:'Peer Analysis',icon:'chart',text:'99215 utilization at 78% vs. peer median 18%. Provider ranks in top 1.3% nationally. Statistically improbable without systematic miscoding.',sev:'high'},
  {date:'Sep 2, 2024',type:'Network Scan',icon:'network',text:'Co-billing relationship identified with Sunrise Medical Group (NPI: 9876543210). Shared patient overlap: 34%.',sev:'med'},
  {date:'Sep 3, 2024',type:'Claims Pull',icon:'file',text:'847 claims reviewed for FY2024. Estimated overbilling vs. peer-adjusted expected: $1.4M.',sev:'high'},
  {date:'Sep 4, 2024',type:'Analyst Review',icon:'user',text:'Assigned to Analyst J. Morrison. Priority: HIGH. Recommended for site visit and records request.',sev:'info'},
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
    reasoning: '47-to-6 code reduction directly contradicts the clinical diversity expected in CMS IOM §30.6.1. The 98% billing concentration in high-reimbursement codes with simultaneous 442% billing growth is not attributable to legitimate specialty focus — peer cohort of 847 providers shows no comparable pattern. OIG FY2024 Work Plan explicitly identifies this pattern.',
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
    icon: Share2, color: C.purple,
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
  {id:'MC-2024-0891',prov:'Advanced Pain Specialists',npi:'1234567890',type:'Billing + Trend',risk:94,status:'Under Review',analyst:'J. Morrison',amt:'$1.4M',date:'Sep 4'},
  {id:'MC-2024-0887',prov:'Sunrise Medical Group',npi:'9876543210',type:'Network',risk:91,status:'Escalated',analyst:'T. Williams',amt:'$1.2M',date:'Sep 2'},
  {id:'MC-2024-0872',prov:'Dr. James Kellerman',npi:'1122334455',type:'Billing',risk:89,status:'Pending',analyst:'Unassigned',amt:'$547K',date:'Sep 1'},
  {id:'MC-2024-0854',prov:'Gulf Coast DME Supply',npi:'5544332211',type:'Billing',risk:87,status:'Under Review',analyst:'M. Johnson',amt:'$890K',date:'Aug 28'},
  {id:'MC-2024-0831',prov:'Premier Diagnostics LLC',npi:'6677889900',type:'Network',risk:83,status:'Closed · Confirmed',analyst:'J. Morrison',amt:'$720K',date:'Aug 15'},
  {id:'MC-2024-0819',prov:'Dr. Maria Santos',npi:'0099887766',type:'Trend',risk:79,status:'Closed · Cleared',analyst:'R. Davis',amt:'—',date:'Aug 10'},
  {id:'MC-2024-0802',prov:'Coastal Rehab Center',npi:'1357924680',type:'Network',risk:74,status:'Pending',analyst:'Unassigned',amt:'$1.1M',date:'Aug 22'},
  {id:'MC-2024-0791',prov:'Dr. Robert Chen',npi:'2468013579',type:'Billing',risk:71,status:'Under Review',analyst:'T. Williams',amt:'$380K',date:'Aug 20'},
];

const canned = {
  codes: "The top 6 HCPCS codes driving 98% of billing are:\n\n• 99215 — Complex office visit (61% of claims)\n• 99214 — Moderate office visit (14%)\n• 64483 — Lumbar nerve block (11%)\n• 62323 — Epidural injection (7%)\n• 72148 — Lumbar MRI (4%)\n• 20610 — Joint injection (3%)\n\nNormal pain management practices bill 30–50+ unique codes. This consolidation to 6 codes is a strong indicator of systematic cherry-picking.",
  compare: "Compared to 847 similar pain management providers in Florida:\n\n• 99215 rate: 78% vs. peer median 21%\n• New patient ratio: 52% vs. 19% median\n• Avg units/claim: 3.8 vs. 1.6 median\n• Monthly billing growth: +442% over 18 months vs. +12% peer average\n\nThis provider ranks in the top 1.3% nationally on 99215 utilization.",
  next: "Recommended investigative steps:\n\n1. Records Request — Pull 50 random patient charts for 99215 claims to validate medical necessity\n2. Site Visit — Physical inspection of facility and patient volume\n3. Beneficiary Interviews — Contact 10–15 patients to verify services\n4. Prepayment Review — Place provider on prepayment edit pending investigation\n\nEstimated timeline: 6–8 weeks. Estimated recovery if confirmed: $1.4M.",
  default: "I can help you analyze specific billing codes, compare this provider to their peers, outline recommended investigative steps, or draft a case summary for your supervisor. What would you like to explore?",
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

// ── DASHBOARD ──────────────────────────────────────────────────────────────────
function Dashboard({ prog }) {
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
function AnomalyFeed({ onSelect, feedback = {}, onFeedback = () => {} }) {
  const [expanded, setExpanded] = useState(null);
  const [filter, setFilter] = useState('All');
  const types = ['All','Billing','Network','Trend'];
  
  // Helper to get latest feedback for provider
  const getLatestFeedback = (npi) => {
    if (!feedback[npi] || !feedback[npi].overall) return null;
    return feedback[npi].overall[0];
  };
  
  let rows = filter === 'All' ? feed : feed.filter(r => r.type.includes(filter));

  return (
    <div style={{ padding:24, display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div>
          <div style={{ ...oxan, fontSize:18, fontWeight:700, color:C.text }}>Anomaly Detection Feed</div>
          <div style={{ fontSize:12, color:C.dim, marginTop:3 }}>{rows.length} of {feed.length} alerts · sorted by risk score</div>
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
        return (
          <div key={r.id} className="fu" style={{
            background:C.s2, border:`1px solid ${expanded===r.id ? C.b2 : (fb ? fbColor+'40' : C.b0)}`,
            borderRadius:10, overflow:'hidden',
            animationDelay:`${i*0.04}s`,
          }}>
          <div onClick={() => setExpanded(expanded===r.id ? null : r.id)} style={{
            display:'grid', gridTemplateColumns:'2.2fr 1fr 110px 110px 80px 160px',
            padding:'14px 16px', cursor:'pointer', alignItems:'center',
          }}>
            <div>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <div style={{ fontSize:14, fontWeight:500, color:C.text }}>{r.name}</div>
                {fb && (
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
            <div style={{ ...oxan, fontSize:13, fontWeight:700, color:C.amber }}>{r.amt}</div>
            <div style={{ display:'flex', gap:7 }}>
              <button onClick={e=>{e.stopPropagation(); onSelect(r);}} style={{
                padding:'5px 11px', borderRadius:6, border:`1px solid ${C.cyan}50`,
                background:`${C.cyan}10`, color:C.cyan, fontSize:11, cursor:'pointer',
              }}>Review</button>
            </div>
          </div>
          {expanded === r.id && (
            <div style={{ borderTop:`1px solid ${C.b0}`, padding:16, background:C.s3 }}>
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
  const p = provider || feed[0];
  const providerId = p.npi;
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

  const reasons = [
    { icon:TrendingUp, label:'HCPCS Consolidation', color:C.red,
      desc:`Unique procedure codes fell from 47 → 6 over 18 months. Top 3 codes now represent 98% of all billing. Pattern is consistent with systematic code selection to maximize reimbursement.`, section:'hcpcs_consolidation' },
    { icon:AlertTriangle, label:'E&M Upcoding', color:C.amber,
      desc:`99215 (highest-complexity visit) accounts for 78% of E&M claims vs. peer median of 18%. Provider ranks in the top 1.3% nationally — statistically improbable without systematic miscoding.`, section:'em_upcoding' },
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
              AI ANALYSIS · 3 ANOMALY SIGNALS DETECTED
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
            {t.badge && <span style={{ marginLeft:6, background:C.cyan, color:'#fff', borderRadius:4, fontSize:9, padding:'1px 5px' }}>NEW</span>}
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
                  <div style={{ fontSize:11, color:C.dim, marginTop:1 }}>Billing collapsed from 47 unique codes to 6 codes — 98% concentration on just 3 high-paying codes</div>
                </div>
              </div>
              <Chip label="HIGH SEVERITY" color={C.red}/>
            </div>
            <div style={{ padding:20, display:'flex', gap:16 }}>
              {/* Left: Dual-axis chart (2/3 width) */}
              <div style={{ flex:2, display:'flex', flexDirection:'column' }}>
                <div style={{ fontSize:11, color:C.muted, marginBottom:12, ...mono }}>CODE DIVERSITY COLLAPSE & CONCENTRATION RISE · 18-MONTH TREND</div>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={hcpcs} margin={{ top:5, right:40, bottom:5, left:-20 }}>
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
                  </AreaChart>
                </ResponsiveContainer>
                <div style={{ display:'flex', gap:14, marginTop:8 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:C.dim }}>
                    <div style={{ width:14, height:2, background:C.red }}/> Unique HCPCS Codes (47 → 6)
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:C.dim }}>
                    <div style={{ width:14, height:2, background:C.amber }}/> Top 3 Code Concentration (38% → 98%)
                  </div>
                </div>
              </div>

              {/* Right: Metrics + Table (1/3 width) */}
              <div style={{ flex:1, display:'flex', flexDirection:'column', gap:12 }}>
                {/* Key metrics */}
                <div style={{ display:'flex', flexDirection:'row', gap:10 }}>
                  {[
                    {v:'47 → 6', l:'Code diversity collapse', c:C.red, sub:'87% reduction in 18 months'},
                    {v:'98%', l:'Top 3 concentration', c:C.amber, sub:'up from 38% baseline'},
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
                  <div style={{ fontSize:10, color:C.muted, marginBottom:10, ...mono }}>TOP 6 CODES · CURRENT MIX</div>
                  <div style={{ display:'flex', flexDirection:'column', gap:6, flex:1 }}>
                    {[
                      {code:'99215', name:'Office visit, level 5', pct:42},
                      {code:'99214', name:'Office visit, level 4', pct:35},
                      {code:'99213', name:'Office visit, level 3', pct:21},
                      {code:'96372', name:'Therapeutic injection', pct:1.2},
                      {code:'36415', name:'Venipuncture', pct:0.5},
                      {code:'85025', name:'CBC', pct:0.3},
                    ].map((row,i)=>(
                      <div key={i} style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', paddingBottom:5, borderBottom: i < 5 ? `1px solid ${C.b0}` : 'none' }}>
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
              <ComponentFeedback section="hcpcs_consolidation" label="HCPCS Code Consolidation Signal" />
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
                  <div style={{ ...oxan, fontWeight:700, fontSize:13, color:C.text }}>Signal 2 · E&M Level Upcoding</div>
                  <div style={{ fontSize:11, color:C.dim, marginTop:1 }}>99215 (highest complexity) used 4× above peer median — statistically improbable without systematic miscoding</div>
                </div>
              </div>
              <Chip label="HIGH SEVERITY" color={C.amber}/>
            </div>
            <div style={{ padding:20, display:'flex', gap:16 }}>
              {/* E&M distribution grouped bar */}
              <div style={{ flex:1 }}>
                <div style={{ fontSize:11, color:C.muted, marginBottom:12, ...mono }}>E&M CODE MIX — THIS PROVIDER vs. PEERS · % OF ALL E&M CLAIMS</div>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={emDist} margin={{ top:5, right:10, bottom:5, left:-20 }}>
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
                <div style={{ fontSize:11, color:C.muted, marginBottom:12, ...mono }}>99215 UTILIZATION RATE OVER TIME · PROVIDER vs. PEER MEDIAN %</div>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={emTrend} margin={{ top:5, right:10, bottom:5, left:-20 }}>
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
                  </AreaChart>
                </ResponsiveContainer>
                <div style={{ display:'flex', gap:14, marginTop:8 }}>
                  {[{c:C.red,l:'This Provider (31% → 78%)'},{c:C.cyan,l:'Peer Median (stable ~19%)'}].map((x,i)=>(
                    <div key={i} style={{ display:'flex', alignItems:'center', gap:6, fontSize:10, color:C.dim }}>
                      <div style={{ width:14, height:2, background:x.c }}/>{x.l}
                    </div>
                  ))}
                </div>
              </div>
              {/* Stats panel */}
              <div style={{ width:160, display:'flex', flexDirection:'column', gap:9 }}>
                {[
                  {v:'78%', l:'Provider 99215 rate', c:C.red, sub:'vs 18% peer median'},
                  {v:'Top 1.3%', l:'Nationally for 99215', c:C.red, sub:'among 847 peers (FL)'},
                  {v:'+147%', l:'Rate rise over 18mo', c:C.amber, sub:'31% → 78%'},
                  {v:'$1.1M', l:'Est. E&M overbilling', c:C.amber, sub:'vs. peer-adjusted expected'},
                ].map((s,i)=>(
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
              <ComponentFeedback section="em_upcoding" label="E&M Upcoding Signal" />
            </div>
          </div>

          {/* ── SIGNAL 3: NETWORK CO-BILLING ───────────────────────────────── */}
          <div style={{ background:C.s2, border:`1px solid ${C.b0}`, borderRadius:12, overflow:'hidden' }}>
            <div style={{ padding:'14px 20px', background:`${C.purple}08`, borderBottom:`1px solid ${C.b0}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                <div style={{ width:24, height:24, borderRadius:6, background:`${C.purple}20`, display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <Share2 size={13} color={C.purple}/>
                </div>
                <div>
                  <div style={{ ...oxan, fontWeight:700, fontSize:13, color:C.text }}>Signal 3 · Suspicious Network Co-billing</div>
                  <div style={{ fontSize:11, color:C.dim, marginTop:1 }}>4 connected providers — all independently flagged — with anomalous shared-patient overlap rates</div>
                </div>
              </div>
              <Chip label="MEDIUM SEVERITY" color={C.purple}/>
            </div>
            <div style={{ padding:20, display:'flex', gap:16 }}>
              {/* SVG Network Diagram */}
              <div style={{ flex:1 }}>
                <div style={{ fontSize:11, color:C.muted, marginBottom:12, ...mono }}>PROVIDER CO-BILLING NETWORK · EDGE WIDTH = SHARED PATIENT OVERLAP %</div>
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
                    {netEdges.map((e,i)=>{
                      const f = netNodes.find(n=>n.id===e.from);
                      const t = netNodes.find(n=>n.id===e.to);
                      const mx = (f.x+t.x)/2, my = (f.y+t.y)/2;
                      return (
                        <g key={i}>
                          <line x1={f.x} y1={f.y} x2={t.x} y2={t.y}
                            stroke={e.from==='aps'||e.to==='aps' ? C.purple : C.muted}
                            strokeWidth={e.w} opacity={0.45} strokeDasharray={e.from!=='aps'&&e.to!=='aps'?'4 3':undefined}/>
                          <rect x={mx-14} y={my-8} width={28} height={15} rx={3}
                            fill={C.s1} stroke={C.b1} strokeWidth={0.8}/>
                          <text x={mx} y={my+4} textAnchor="middle"
                            fill={C.dim} fontSize={8} fontFamily="IBM Plex Mono">{e.overlap}%</text>
                        </g>
                      );
                    })}
                    {/* Nodes */}
                    {netNodes.map((n,i)=>{
                      const isSubject = n.id==='aps';
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
                <div style={{ fontSize:11, color:C.muted, marginBottom:0, ...mono }}>CONNECTED FLAGGED PROVIDERS · SHARED PATIENT ANALYSIS</div>
                <div style={{ background:C.s3, border:`1px solid ${C.b0}`, borderRadius:10, overflow:'hidden', flex:1 }}>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 60px 55px 60px 80px',
                    padding:'8px 12px', borderBottom:`1px solid ${C.b0}`,
                    ...mono, fontSize:9, color:C.muted, letterSpacing:'0.06em', background:C.s1 }}>
                    <span>PROVIDER</span><span>OVERLAP</span><span>VOL</span><span>RISK</span><span>STATUS</span>
                  </div>
                  {netTable.map((r,i)=>(
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
                    All 4 connected providers are independently flagged. Combined shared-patient volume of{' '}
                    <span style={{ color:C.text, fontWeight:500 }}>636 beneficiaries</span>. Referral density is{' '}
                    <span style={{ color:C.purple, fontWeight:500 }}>4.2× expected</span> for unaffiliated practices — consistent with a coordinated billing arrangement.
                  </div>
                </div>
              </div>
            </div>
            {/* Component-level feedback for Signal 3 */}
            <div style={{ padding:'0 20px 16px 20px' }}>
              <ComponentFeedback section="network_cobilling" label="Network Co-billing Signal" />
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
                <span style={{ padding:'2px 8px', borderRadius:4, background:`${C.green}18`, border:`1px solid ${C.green}40`, fontSize:9, color:C.green, ...mono }}>PKG v2.4</span>
              </div>
              <div style={{ fontSize:12, color:C.dim, lineHeight:1.6 }}>
                3 anomaly signals queried against CMS policy corpus · <span style={{ color:C.text }}>8 policy sections retrieved</span> · Grounding complete.
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
          {pkgSignals.map((sig, si) => {
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
            {evLog.map((ev, i) => {
              const iconColor = ev.sev==='high' ? C.red : ev.sev==='med' ? C.amber : C.cyan;
              const Icon = ev.icon==='bot' ? Bot : ev.icon==='chart' ? TrendingUp : ev.icon==='network' ? Share2 : ev.icon==='file' ? FileText : User;
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
                    {i < evLog.length-1 && <div style={{ width:1, flex:1, background:C.b1, marginTop:4 }} />}
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
          <div style={{ fontSize:11, color:C.dim, marginBottom:18 }}>Estimated monthly Medicare billing ($K) · showing 442% growth over 18 months</div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={hcpcs} margin={{ top:5, right:20, bottom:5, left:-10 }}>
              <defs>
                <linearGradient id="gBill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.amber} stopOpacity={0.4}/>
                  <stop offset="95%" stopColor={C.amber} stopOpacity={0.02}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={C.b0} />
              <XAxis dataKey="m" tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} interval={2} />
              <YAxis tick={{ fill:C.muted, fontSize:9, fontFamily:'IBM Plex Mono' }} axisLine={false} tickLine={false} tickFormatter={v=>`$${v}K`} />
              <Tooltip {...tipStyle} formatter={(v)=>[`$${v}K`,'Monthly Billing']} />
              <Area type="monotone" dataKey="bill" stroke={C.amber} strokeWidth={2.5} fill="url(#gBill)" name="Billing ($K)" />
            </AreaChart>
          </ResponsiveContainer>
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

  const totExposure = '$323M';
  const filteredGaps = policyGaps.filter(g => prog==='medicare' ? g.programImpact!=='medicaid' : prog==='medicaid' ? g.programImpact!=='medicare' : true);

  return (
    <div style={{ padding:24, display:'flex', flexDirection:'column', gap:18 }}>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div>
          <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:5 }}>
            <div style={{ padding:8, borderRadius:9, background:`${C.green}15` }}><Landmark size={18} color={C.green}/></div>
            <div style={{ ...oxan, fontSize:18, fontWeight:700, color:C.text }}>Policy Intelligence</div>
            <span style={{ padding:'2px 9px', borderRadius:5, background:`${C.green}15`, border:`1px solid ${C.green}35`, fontSize:9, ...mono, color:C.green }}>FOR CMS LEADERSHIP</span>
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
          { icon:AlertCircle, label:'Policy Gaps Identified', value:'14', sub:'Across CMS, CFR, SSA, OIG corpus', color:C.red },
          { icon:DollarSign, label:'Total Estimated Exposure', value:totExposure, sub:'Attributable to policy gaps', color:C.amber },
          { icon:TriangleAlert, label:'Cases Exposing Gaps', value:'91', sub:'Q4 2024 YTD', color:C.amber },
          { icon:Lightbulb, label:'Policy Change Recs', value:'14', sub:'Actionable recommendations', color:C.green },
          { icon:Globe, label:'Programs Impacted', value:'Both', sub:'Medicare FFS & Medicaid FFS', color:C.purple },
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
            {[
              {x:170,y:55,r:18,c:C.red,  l:'G1',label:'Code Concentration'},
              {x:235,y:75,r:15,c:C.amber,l:'G2',label:'Outlier Threshold'},
              {x:135,y:95,r:13,c:C.amber,l:'G3',label:'AKS Threshold'},
              {x:175,y:120,r:11,c:C.cyan, l:'G4',label:'NCCI Edit Lag'},
            ].map((b,i)=>(
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
function CaseMgmt({ feedback = {}, onFeedback = () => {} }) {
  const sc = { 'Under Review':C.cyan, 'Escalated':C.red, 'Pending':C.amber, 'Closed · Confirmed':C.green, 'Closed · Cleared':C.muted };
  const summary = [
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
          <div style={{ fontSize:12, color:C.dim, marginTop:3 }}>8 active cases · 1 escalated · $6.2M under review</div>
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
          display:'grid', gridTemplateColumns:'150px 400px 2px 1fr 1fr 1fr 2px 1fr 1fr 1fr',
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
          display:'grid', gridTemplateColumns:'150px 400px 2px 1fr 1fr 1fr 2px 1fr 1fr 1fr',
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
        {cases.map((c, i) => {
          const fb = getLatestFeedback(c.npi);
          const suggestedAction = getSuggestedAction(c);
          const ActionIcon = suggestedAction.icon;
          const riskColor = c.risk >= 90 ? C.red : c.risk >= 75 ? C.amber : C.green;
          return (
          <div key={c.id} style={{
            display:'grid', gridTemplateColumns:'150px 400px 2px 1fr 1fr 1fr 2px 1fr 1fr 1fr',
            padding:'13px 18px', alignItems:'center',
            borderBottom: i < cases.length-1 ? `1px solid ${C.b0}` : 'none',
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
              {fb ? (
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
function AIPanel({ onClose }) {
  const [input, setInput] = useState('');
  const [msgs, setMsgs] = useState([{
    role:'assistant',
    text:"I've analyzed Advanced Pain Specialists (NPI: 1234567890) and identified 3 high-confidence anomaly signals:\n\n1. HCPCS Consolidation — Billed 47 unique procedure codes in Mar 2023. By Aug 2024, just 6 codes account for 98% of billing. Consistent with systematic code cherry-picking to maximize reimbursement.\n\n2. E&M Upcoding — 99215 (highest-complexity visit) is 78% of all E&M claims vs. peer median of 18%. This provider ranks in the top 1.3% nationally — statistically improbable without systematic miscoding.\n\n3. Network Co-billing — 34% of patients share treatment history with Sunrise Medical Group (also flagged). Mutual referral density is 4.2× expected for unrelated practices.\n\nEstimated overpayment risk: $1.4M (FY2024)",
  }]);

  const send = () => {
    if (!input.trim()) return;
    const q = input.toLowerCase();
    setMsgs(m => [...m, { role:'user', text:input }]);
    setInput('');
    const key = q.includes('code') ? 'codes' : q.includes('compar') || q.includes('peer') ? 'compare' : q.includes('next') || q.includes('recommend') || q.includes('step') ? 'next' : 'default';
    setTimeout(() => setMsgs(m => [...m, { role:'assistant', text:canned[key] }]), 600);
  };

  const prompts = ['What codes are involved?','Compare to peers','Recommend next steps'];

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
            <div style={{ ...mono, fontSize:10, color:C.cyan, marginTop:1 }}>● ACTIVE · Advanced Pain Specialists</div>
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
                  <span style={{ padding:'1px 5px', borderRadius:3, background:`${C.green}18`, border:`1px solid ${C.green}35`, fontSize:8, color:C.green, ...mono }}>PKG</span>
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
                {pd.label}
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
            {screen==='feed'      && <AnomalyFeed onSelect={handleSelect} feedback={feedback} onFeedback={handleFeedback}/>}
            {screen==='provider'  && <ProviderDive provider={selProv} prog={prog} feedback={feedback} onFeedback={handleFeedback}/>}
            {screen==='cases'     && <CaseMgmt feedback={feedback} onFeedback={handleFeedback}/>}
            {screen==='policy'    && <PolicyIntel prog={prog}/>}
          </div>
        </div>

        {aiOpen && <AIPanel onClose={()=>setAiOpen(false)}/>}
      </div>
    </>
  );
}
