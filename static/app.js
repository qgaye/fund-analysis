const form = document.querySelector("#fund-form");
const codeInput = document.querySelector("#fund-code");
const inputHelp = document.querySelector("#input-help");
const landingState = document.querySelector("#landing-state");
const loadingState = document.querySelector("#loading-state");
const errorState = document.querySelector("#error-state");
const errorMessage = document.querySelector("#error-message");
const results = document.querySelector("#results");
const refreshButton = document.querySelector("#refresh-button");
const favoriteButton = document.querySelector("#favorite-button");

let currentCode = "";
let currentFundSnapshot = null;
let currentHoldings = null;
let currentHoldingType = "股票";
let currentBondStructureView = "品种";
let currentHoldingsPeriodKey = "";
let currentQuarterReports = [];
let holdingsRequestId = 0;
let currentNavHistory = {};
let currentNavRange = "1y";
let currentNavMetric = "累计收益率";
let currentCustomRange = { start: "", end: "" };
let currentInvestmentMode = "single";
let currentDividends = [];
let navPlotPoints = [];
let navChartDimensions = { width: 1000, height: 360 };
let currentPeriodicUnit = "year";
let currentPerformance = {};
let currentTrackBenchmark = null;
let currentTrackBenchmarkKey = "";
let performanceCompositeSpec = "";
let trackBenchmarkRequestId = 0;
let benchmarkPlotPoints = [];
let currentStockDetail = null;
let currentStockRange = "1y";
let currentStockCode = "";
let currentStockFallback = {};
let stockDetailRequestId = 0;
let stockPlotPoints = [];
const trackBenchmarkCache = new Map();
let hs300Series = null;
let hs300RequestId = 0;

// 2005 年后 A 股主要牛熊周期（以上证/沪深300阶段高低点月份为准）。
const bullBearCycles = [
  {
    type: "bull",
    start: "2005-06-01",
    end: "2007-10-31",
    label: "2005–07 大牛市",
    points: "上证综指 998 → 6124 点",
    driver: "股权分置改革落地、人民币升值预期、经济高速增长与流动性充裕共同推动的全面大牛市。",
  },
  {
    type: "bear",
    start: "2007-10-31",
    end: "2008-10-31",
    label: "2008 熊市",
    points: "上证综指 6124 → 1664 点",
    driver: "全球金融危机爆发、外需骤降与前期估值泡沫破裂，市场单边急跌。",
  },
  {
    type: "bull",
    start: "2008-10-31",
    end: "2009-08-31",
    label: "2009 反弹",
    points: "上证综指 1664 → 3478 点",
    driver: "“四万亿”经济刺激计划与信贷天量投放带动的快速反弹。",
  },
  {
    type: "bear",
    start: "2009-08-31",
    end: "2014-06-30",
    label: "2009–14 慢熊",
    points: "上证综指 3478 → 约 2000 点",
    driver: "经济增速换挡、IPO 扩容与去产能压制估值，长达数年的震荡阴跌。",
  },
  {
    type: "bull",
    start: "2014-07-01",
    end: "2015-06-12",
    label: "2014–15 杠杆牛",
    points: "上证综指 约 2000 → 5178 点",
    driver: "多次降息降准、融资融券与场外配资杠杆资金涌入、改革牛预期驱动的快速上涨。",
  },
  {
    type: "bear",
    start: "2015-06-12",
    end: "2016-01-28",
    label: "2015 股灾",
    points: "上证综指 5178 → 2638 点",
    driver: "清理场外配资、去杠杆引发流动性踩踏，年初熔断机制加剧下跌。",
  },
  {
    type: "bull",
    start: "2019-01-04",
    end: "2021-02-18",
    label: "2019–21 结构牛",
    points: "沪深300 约 2935 → 5930 点",
    driver: "外资持续流入、注册制推进与核心资产（白马、消费、新能源）抱团行情驱动的结构性牛市。",
  },
  {
    type: "bear",
    start: "2021-02-18",
    end: "2024-02-05",
    label: "2021–24 调整",
    points: "沪深300 5930 → 约 3180 点",
    driver: "核心资产抱团瓦解，叠加地产风险、监管收紧与经济复苏不及预期，市场持续调整。",
  },
  {
    type: "bull",
    start: "2024-09-24",
    end: new Date().toISOString().slice(0, 10),
    label: "2024–至今 反攻",
    points: "沪深300 自 3200 点区间回升",
    driver: "“924”一揽子货币金融政策集中发力、政治局会议超预期定调，风险偏好修复带动市场强势反弹。",
  },
];

const palette = [
  "#d33b28",
  "#e07e2e",
  "#d7a928",
  "#8e9f36",
  "#14745a",
  "#337f86",
  "#4e6a98",
  "#765c87",
  "#9a5264",
  "#5f645c",
];

const nonPolicyFinancialBondGuide = {
  tone: "credit",
  introduction:
    "由商业银行、证券公司、保险公司等金融机构发行，偿债能力主要取决于发行机构自身信用；若是二级资本债或永续债，还可能带有次级、减记或不赎回条款。",
  features:
    "通常比同期限利率债提供更高票息或信用利差。发行人监管强、信息较充分，但不同机构与具体资本工具之间差异很大。",
  return:
    "票息收入、信用利差收窄带来的价格上涨，以及随市场利率下降产生的资本利得。",
  risk:
    "发行人信用恶化、评级下调、信用利差走阔；资本补充工具还要关注次级清偿、减记、转股和赎回不确定性。",
  watch:
    "资本充足率、资产质量、不良率、盈利与拨备，以及债券是否含次级、永续、减记或赎回条款。",
  riskLevel: "中等 · 信用与条款主导",
  portfolio:
    "占比较高时，组合收益通常更依赖金融机构信用利差，而不只是无风险利率变化；应继续观察发行人集中度和资本工具条款。",
};

const convertibleBondGuide = {
  tone: "hybrid",
  introduction:
    "兼具债券和权益期权属性。可转债可按约定转换为发行公司股票，可交换债则交换为发行人持有的其他公司股票。",
  features:
    "正股上涨时通常具有向上弹性，正股走弱时可能获得一定债底支撑；实际表现会受转股价、赎回、回售和下修条款影响。",
  return:
    "较低票息、正股上涨带来的转股价值提升、估值溢价变化，以及条款博弈产生的收益。",
  risk:
    "正股下跌、估值溢价压缩、发行人违约、强制赎回与流动性风险；债底并不等于本金绝对安全。",
  watch:
    "正股基本面、转股价值与转股溢价率、到期收益率、赎回与回售触发条件、剩余规模和信用资质。",
  riskLevel: "中高 · 股债双重驱动",
  portfolio:
    "占比较高时，基金净值可能明显增加股票市场敏感度，不能仅按传统固收产品理解其波动。",
};

const assetBackedGuide = {
  tone: "structured",
  introduction:
    "以贷款、应收账款、租赁债权等资产池未来现金流作为主要偿付来源，并通常通过优先/次级分层和增信安排形成不同风险档次。",
  features:
    "偿付表现不仅取决于发起机构，还取决于底层资产质量、现金流分散度、交易结构和增信机制，分析维度比普通信用债更多。",
  return:
    "基础票息、结构复杂度与流动性补偿，以及底层资产表现优于预期带来的估值改善。",
  risk:
    "底层资产违约、早偿或延期、现金流错配、增信失效、模型假设偏差和二级市场流动性不足。",
  watch:
    "底层资产类型与集中度、逾期违约率、优先级厚度、超额覆盖、担保增信、现金流分配顺序及早偿条款。",
  riskLevel: "中等至较高 · 结构主导",
  portfolio:
    "占比较高时，需要穿透底层资产和分层结构判断风险，单看产品评级或票息容易低估尾部损失与流动性风险。",
};

const certificateOfDepositGuide = {
  tone: "money",
  introduction:
    "银行业存款类金融机构在银行间市场发行的记账式定期存款凭证，通常期限较短，是货币市场与短久期组合的重要工具。",
  features:
    "久期通常较短、交易标准化，收益水平与银行负债需求、货币市场资金面和发行机构信用相关。",
  return:
    "贴现或票息收入，以及资金利率下降、同业存单利差收窄带来的小幅资本利得。",
  risk:
    "发行银行信用恶化、资金面收紧导致价格波动、流动性下降，以及到期后再投资收益降低。",
  watch:
    "发行银行资质、期限、主体评级、同业存单到期收益率、银行负债压力和市场资金松紧。",
  riskLevel: "通常偏低至中等 · 短久期信用",
  portfolio:
    "占比较高通常意味着组合偏短久期和流动性管理，但仍承受银行信用利差与滚动再投资风险。",
};

const bondStructureGuideCatalog = {
  国家债券: {
    tone: "rate",
    introduction:
      "由中央政府发行并以国家信用为基础，通常包括记账式国债等，是人民币债券市场最典型的利率债。",
    features:
      "信用风险通常较低、定价透明、流动性较好，价格主要随无风险利率和期限变化。",
    return:
      "票息收入、持有至到期的本金回收，以及市场利率下降时的价格上涨。",
    risk:
      "利率上升导致价格下跌；长久期品种波动更大，另有通胀侵蚀实际收益和再投资风险。",
    watch: "剩余期限、久期、到期收益率、收益率曲线形态、通胀与货币政策预期。",
    riskLevel: "通常较低 · 利率主导",
    portfolio:
      "占比较高通常有助于降低信用尾部风险，但组合仍可能因久期较长而出现明显净值波动。",
  },
  央行票据: {
    tone: "rate",
    introduction:
      "由中央银行发行、用于调节基础货币和市场流动性的债务工具，信用基础与央行相关，通常期限偏短。",
    features:
      "政策工具属性突出，信用风险通常较低，定价更敏感于短端资金利率和货币政策操作。",
    return: "贴现或票息收入，以及短端市场利率下降带来的价格收益。",
    risk:
      "短端利率上升、流动性变化和到期再投资收益下降；通常价格波动小于长久期债券。",
    watch: "公开市场操作、政策利率、银行间资金面、期限和到期收益率。",
    riskLevel: "通常较低 · 短端利率主导",
    portfolio: "占比较高通常体现流动性管理和短久期配置，收益弹性一般相对有限。",
  },
  政策性金融债: {
    tone: "rate",
    introduction:
      "由国家开发银行、中国进出口银行、中国农业发展银行等政策性银行发行，市场通常按利率债交易。",
    features:
      "信用资质高、银行间市场成交活跃，收益率一般略高于同期限国债，是债券基金常用的久期与交易工具。",
    return: "票息、国债与政策性金融债之间的利差变化，以及利率下行带来的资本利得。",
    risk:
      "市场利率上升和久期风险是主要来源；极端市场下也可能出现流动性与利差波动。",
    watch: "久期、到期收益率、与国债利差、活跃券流动性和货币政策方向。",
    riskLevel: "通常较低 · 久期主导",
    portfolio:
      "占比较高通常意味着信用风险较低，但基金对利率方向和收益率曲线变化可能更加敏感。",
  },
  地方政府债: {
    tone: "rate",
    introduction:
      "由省、自治区、直辖市等地方政府依法发行，资金多用于公益性项目或偿还符合规定的政府债务。",
    features:
      "以地方政府财政信用为基础，期限常偏长，不同地区、期限和券种的交易活跃度存在差异。",
    return: "票息、地方债与国债之间的利差，以及市场利率下降带来的价格收益。",
    risk:
      "久期和利率风险、区域财政与债务压力、供给冲击及部分券种二级市场流动性不足。",
    watch: "地区财政实力、债务负担、再融资安排、期限、与国债利差和市场成交活跃度。",
    riskLevel: "通常较低至中等 · 利率与区域财政",
    portfolio:
      "占比较高往往带来较稳定票息，但需留意长久期波动以及区域和期限集中度。",
  },
  "金融债（不含政策性）": nonPolicyFinancialBondGuide,
  金融债: nonPolicyFinancialBondGuide,
  企业债券: {
    tone: "credit",
    introduction:
      "由企业发行并承担还本付息责任的信用债，偿付能力与企业经营、现金流、资产负债表和外部支持密切相关。",
    features:
      "相对利率债通常提供信用利差，不同行业、所有制、地区、担保和评级之间分化显著。",
    return: "票息、信用利差收窄、评级改善和市场利率下降带来的价格收益。",
    risk:
      "违约与回收损失、评级下调、信用利差走阔、行业景气下行、担保失效和流动性不足。",
    watch: "经营现金流、债务到期结构、杠杆、融资渠道、行业周期、外部支持与债券增信条款。",
    riskLevel: "中等至较高 · 企业信用主导",
    portfolio:
      "占比较高通常有利于提高票息，但会增强基金对发行人、行业和区域信用周期的敏感度。",
  },
  企业短期融资券: {
    tone: "credit",
    introduction:
      "非金融企业在银行间市场发行的短期债务融资工具，通常用于补充营运资金或置换短期负债。",
    features:
      "期限较短、久期有限，但发行人需要持续依靠经营现金流或再融资偿付到期债务。",
    return: "短期票息或贴现收益、信用利差补偿，以及资金利率变化带来的小幅价格收益。",
    risk:
      "发行人短期流动性紧张、再融资受阻和信用事件；临近到期并不代表没有违约风险。",
    watch: "未来一年到期债务、货币资金、授信与融资渠道、短期现金流、主体评级和担保。",
    riskLevel: "中等 · 短期信用与再融资",
    portfolio:
      "占比较高通常压低组合久期，但会增加对企业短期流动性和滚动融资环境的依赖。",
  },
  中期票据: {
    tone: "credit",
    introduction:
      "非金融企业在银行间市场注册发行的债务融资工具，期限通常长于短期融资券，可分期发行。",
    features:
      "以发行人主体信用为核心，期限和条款较丰富，是信用债基金获取中长期票息的重要品种。",
    return: "票息、信用利差收窄、主体资质改善，以及利率下降带来的资本利得。",
    risk:
      "发行人违约、评级下调、信用利差走阔、行业与区域集中、久期波动和流动性不足。",
    watch: "主体现金流与杠杆、行业景气、债务期限结构、评级迁移、信用利差和成交活跃度。",
    riskLevel: "中等至较高 · 信用与久期",
    portfolio:
      "占比较高时，票息贡献通常较重要，同时基金净值也更容易受信用利差和发行人集中度影响。",
  },
  同业存单: certificateOfDepositGuide,
  资产支持证券: assetBackedGuide,
  "可转债（可交换债）": convertibleBondGuide,
  其他: {
    tone: "other",
    introduction:
      "季报未能归入标准品种的债券资产汇总项，可能包含特殊工具、分类差异或报告中的补充项目。",
    features:
      "内部构成可能不一致，不能仅凭“其他”判断信用、期限或流动性特征。",
    return: "取决于其实际包含的具体工具，可能来自票息、利差、权益期权或结构化现金流。",
    risk: "分类不透明本身就是风险，具体风险需回到基金季报和底层证券逐项确认。",
    watch: "季报附注、底层证券名称、发行人、期限、评级、交易场所和特殊条款。",
    riskLevel: "不确定 · 需穿透识别",
    portfolio: "占比较高时应优先查阅原始季报，确认“其他”实际由哪些工具构成。",
  },
  利率债: {
    tone: "rate",
    introduction:
      "本项目将国债、央票、政策性金融债和地方政府债归入利率债，其价格主要受无风险利率、期限和流动性变化影响。",
    features:
      "信用尾部风险通常低于普通信用债，但并非低波动资产；久期越长，对利率变化越敏感。",
    return: "票息、收益率下行带来的资本利得，以及不同期限与券种之间的利差交易。",
    risk: "利率上行、收益率曲线变化、长久期波动、通胀和再投资风险。",
    watch: "组合久期、期限分布、收益率曲线、货币政策、通胀和债券供给。",
    riskLevel: "信用通常较低 · 利率主导",
    portfolio:
      "占比较高通常降低信用违约暴露，但基金收益对利率方向和久期管理能力会更敏感。",
  },
  信用债: {
    tone: "credit",
    introduction:
      "本项目将非政策性金融债、企业债、短期融资券和中期票据归入信用债，偿付依赖具体发行人的信用。",
    features:
      "相对利率债通常提供更高票息或信用利差，用于补偿违约、评级迁移和流动性等风险。",
    return: "票息、信用利差收窄、评级改善，以及市场利率下降带来的价格收益。",
    risk: "违约与回收损失、评级下调、利差走阔、行业区域集中和流动性不足。",
    watch: "发行人集中度、评级分布、行业与区域暴露、利差、现金流和债务到期压力。",
    riskLevel: "中等至较高 · 信用主导",
    portfolio:
      "占比较高通常提高票息潜力，也会放大信用周期、个券选择和流动性管理对基金表现的影响。",
  },
  可转债: convertibleBondGuide,
};

const navMetricConfig = {
  累计收益率: {
    valueKey: "累计收益率",
    subtitle: "所选区间首日归零的收益走势",
    note: "区间收益将所选区间首个可用点视为 0%，用于观察这段持有期内的涨跌；“成立以来”仅作为长期研究选项。",
    tooltipLabel: "区间收益",
    unit: "%",
  },
  阶段收益: {
    valueKey: "累计收益率",
    subtitle: "各阶段涨幅、相对赛道表现及风险收益效率",
    note: "夏普比率和卡玛比率仅统计近 1 年、近 3 年和近 5 年；达到 1 标记“良好”，达到 2 标记“优秀”。",
    tooltipLabel: "阶段涨幅",
    unit: "%",
  },
  累计净值: {
    valueKey: "累计净值",
    subtitle: "将历史现金分红加回后的净值走势",
    note: "累计净值将历史现金分红加回，减少除息断层；首末变化不等同于分红再投资收益率。",
    tooltipLabel: "累计净值",
    unit: "元",
  },
  分红记录: {
    valueKey: "每份分红",
    subtitle: "现金分红事件与每份分红金额",
    note: "分红会使单位净值在除息日相应下降，本身不是额外收益；累计净值用于观察将历史现金分红加回后的走势。",
    tooltipLabel: "分红记录",
    unit: "元",
  },
  周期收益: {
    valueKey: "累计净值",
    subtitle: "各自然年 / 季度 / 月内的独立涨跌幅",
    note: "基金按累计净值计算并与所选赛道采用相同起止日；每行展示自然年 / 季度 / 月内的基金、赛道和相对涨幅。",
    tooltipLabel: "周期涨幅",
    unit: "%",
  },
  回撤修复: {
    valueKey: "累计收益率",
    subtitle: "区间收益曲线中的最大回撤与修复阶段",
    note: "基金与所选赛道采用相同区间计算最大回撤；基金以绿色/红色标出回撤与修复，蓝色标出赛道对应阶段，修复天数按自然日计算。",
    tooltipLabel: "区间收益",
    unit: "%",
  },
  牛熊周期: {
    valueKey: "累计净值",
    subtitle: "2005 年后各轮 A 股牛熊周期内本基金与沪深300的累计涨跌幅",
    note: "每个牛熊周期内本基金（红）与沪深300（蓝）各自以该周期首个可用净值归零，用于对比同一轮行情中的表现；仅展示本基金存续期覆盖到的周期。",
    tooltipLabel: "周期涨幅",
    unit: "%",
  },
};

function text(selector, value, fallback = "暂无数据") {
  const element = document.querySelector(selector);
  element.textContent =
    value === null || value === undefined || value === "" ? fallback : value;
}

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(2)}%`;
}

function formatCurrency(value, signed = false) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  const numeric = Number(value);
  const absolute = Math.abs(numeric).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (!signed) return `¥${absolute}`;
  if (numeric > 0) return `+¥${absolute}`;
  if (numeric < 0) return `-¥${absolute}`;
  return "¥0.00";
}

function movementClass(value) {
  const numeric = Number(value);
  if (numeric > 0) return "positive-text";
  if (numeric < 0) return "negative-text";
  return "";
}

function setView(view) {
  landingState.hidden = view !== "landing";
  loadingState.hidden = view !== "loading";
  errorState.hidden = view !== "error";
  results.hidden = view !== "results";
}

function validateCode(value) {
  return /^\d{6}$/.test(value);
}

function normalizeStockCode(value) {
  const text = String(value ?? "").trim();
  if (/^\d{5}$/.test(text)) return text; // 港股
  if (/^\d{1,6}$/.test(text)) return text.padStart(6, "0"); // A 股
  return text;
}

function validateStockCode(value) {
  return /^\d{6}$/.test(value) || /^\d{5}$/.test(value);
}

function isHkStockCode(value) {
  return /^\d{5}$/.test(String(value ?? "").trim());
}

function fundXueqiuUrl(code) {
  const normalized = String(code ?? "").trim();
  return /^\d{6}$/.test(normalized)
    ? `https://xueqiu.com/S/F${normalized}`
    : "";
}

function stockXueqiuUrl(code, market = "") {
  const normalized = normalizeStockCode(code);
  if (/^\d{5}$/.test(normalized)) {
    return `https://xueqiu.com/S/${normalized}`;
  }
  if (!/^\d{6}$/.test(normalized)) return "";
  const marketName = String(market ?? "");
  const isBeijing =
    marketName.includes("北京") ||
    normalized.startsWith("4") ||
    normalized.startsWith("8") ||
    normalized.startsWith("92");
  const isShanghai =
    marketName.includes("上海") ||
    normalized.startsWith("5") ||
    normalized.startsWith("6") ||
    normalized.startsWith("9");
  const prefix = isBeijing ? "BJ" : isShanghai ? "SH" : "SZ";
  return `https://xueqiu.com/S/${prefix}${normalized}`;
}

function bondOfficialLink(row) {
  const query = [row?.债券名称, row?.债券代码]
    .map((value) => String(value ?? "").trim())
    .filter(Boolean)
    .join(" ");
  return query
    ? `https://www.google.com/search?q=${encodeURIComponent(query)}`
    : "";
}

function stockCurrencyUnit(currency, market) {
  if (currency === "HKD" || market === "HK") return "港元";
  if (currency === "USD") return "美元";
  return "元";
}

function showInputError(message) {
  inputHelp.textContent = message;
  inputHelp.classList.add("invalid");
  codeInput.setAttribute("aria-invalid", "true");
}

function clearInputError() {
  inputHelp.textContent = "支持六位代码、中文名称及拼音首字母";
  inputHelp.classList.remove("invalid");
  codeInput.removeAttribute("aria-invalid");
}

function benchmarkReturnBetween(start, end, previousEndPoint = false) {
  const rows = currentTrackBenchmark?.明细 ?? [];
  if (rows.length < 2 || !start || !end) return null;
  const endIndex = rows.findLastIndex((row) => row.日期 <= end);
  if (endIndex < 1) return null;
  let startIndex = previousEndPoint
    ? endIndex - 1
    : rows.findLastIndex((row) => row.日期 <= start);
  if (startIndex < 0) {
    startIndex = rows.findIndex((row) => row.日期 >= start);
  }
  if (startIndex < 0 || startIndex >= endIndex) return null;
  const startValue = Number(rows[startIndex].指数值);
  const endValue = Number(rows[endIndex].指数值);
  if (
    !Number.isFinite(startValue) ||
    !Number.isFinite(endValue) ||
    startValue <= 0
  ) {
    return null;
  }
  return (endValue / startValue - 1) * 100;
}

function shiftIsoDate(isoDate, { days = 0, months = 0, years = 0 }) {
  const value = new Date(`${isoDate}T12:00:00Z`);
  if (years || months) {
    const targetDay = value.getUTCDate();
    value.setUTCDate(1);
    value.setUTCFullYear(value.getUTCFullYear() + years);
    value.setUTCMonth(value.getUTCMonth() + months);
    const lastDay = new Date(
      Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 1, 0),
    ).getUTCDate();
    value.setUTCDate(Math.min(targetDay, lastDay));
  }
  if (days) value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function benchmarkStageReturn(key) {
  const navRows = currentNavHistory?.累计净值?.明细 ?? [];
  const end = navRows.at(-1)?.日期;
  if (!end) return null;
  if (key === "日涨幅") {
    return benchmarkReturnBetween(end, end, true);
  }
  const startByKey = {
    近1月: shiftIsoDate(end, { months: -1 }),
    近3月: shiftIsoDate(end, { months: -3 }),
    近6月: shiftIsoDate(end, { months: -6 }),
    今年以来: `${end.slice(0, 4)}-01-01`,
    近1年: shiftIsoDate(end, { years: -1 }),
    近3年: shiftIsoDate(end, { years: -3 }),
    近5年: shiftIsoDate(end, { years: -5 }),
    成立以来: navRows[0]?.日期,
  };
  return benchmarkReturnBetween(startByKey[key], end);
}

function optionalNumber(value) {
  if (value == null || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

const STAGE_RISK_FREE_RATE = 0.02;
const TRADING_DAYS_PER_YEAR = 252;
const ANNUAL_RISK_PERIOD_KEYS = new Set(["近1年", "近3年", "近5年"]);

function stageRiskIndexRows(key) {
  const ranges = currentNavHistory?.累计收益率?.区间 ?? {};
  const rangeByKey = {
    近1月: "1m",
    近3月: "3m",
    近6月: "6m",
    近1年: "1y",
    近3年: "3y",
    近5年: "5y",
    成立以来: "all",
  };
  let rows = [];
  if (key === "日涨幅") {
    rows = (ranges["1m"] ?? ranges.all ?? []).slice(-2);
  } else if (key === "今年以来") {
    const source = ranges["1y"] ?? ranges.all ?? [];
    const endDate = source.at(-1)?.日期;
    if (endDate) {
      const cutoff = `${endDate.slice(0, 4)}-01-01`;
      const firstInYear = source.findIndex((row) => row.日期 >= cutoff);
      rows = firstInYear < 0
        ? []
        : source.slice(Math.max(0, firstInYear - 1));
    }
  } else {
    rows = ranges[rangeByKey[key]] ?? [];
  }

  let normalized = rows
    .map((row) => ({
      date: row.日期,
      index: 1 + Number(row.累计收益率) / 100,
    }))
    .filter((row) => row.date && Number.isFinite(row.index) && row.index > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (normalized.length >= 2) return normalized;

  // 历史收益接口偶尔缺少单个阶段，退回累计净值并按相同截止日切片。
  const cumulativeRows = (currentNavHistory?.累计净值?.明细 ?? [])
    .map((row) => ({
      date: row.日期,
      index: Number(row.累计净值),
    }))
    .filter((row) => row.date && Number.isFinite(row.index) && row.index > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (cumulativeRows.length < 2) return [];
  if (key === "日涨幅") return cumulativeRows.slice(-2);
  if (key === "成立以来") return cumulativeRows;

  const endDate = cumulativeRows.at(-1).date;
  const cutoffByKey = {
    近1月: shiftIsoDate(endDate, { months: -1 }),
    近3月: shiftIsoDate(endDate, { months: -3 }),
    近6月: shiftIsoDate(endDate, { months: -6 }),
    今年以来: `${endDate.slice(0, 4)}-01-01`,
    近1年: shiftIsoDate(endDate, { years: -1 }),
    近3年: shiftIsoDate(endDate, { years: -3 }),
    近5年: shiftIsoDate(endDate, { years: -5 }),
  };
  const cutoff = cutoffByKey[key];
  const firstInRange = cumulativeRows.findIndex((row) => row.date >= cutoff);
  normalized = firstInRange < 0
    ? []
    : cumulativeRows.slice(Math.max(0, firstInRange - 1));
  return normalized;
}

function calculateStageRiskMetrics(key) {
  if (!ANNUAL_RISK_PERIOD_KEYS.has(key)) {
    return { sharpe: null, calmar: null };
  }
  const rows = stageRiskIndexRows(key);
  if (rows.length < 3) return { sharpe: null, calmar: null };

  const elapsedDays = daysBetween(rows[0].date, rows.at(-1).date);
  const startValue = rows[0].index;
  const endValue = rows.at(-1).index;
  if (!elapsedDays || startValue <= 0 || endValue <= 0) {
    return { sharpe: null, calmar: null };
  }

  const annualizedReturn =
    (endValue / startValue) ** (365.25 / elapsedDays) - 1;
  const dailyReturns = rows.slice(1).map((row, index) =>
    row.index / rows[index].index - 1,
  );
  let sharpe = null;
  if (dailyReturns.length >= 2) {
    const average = dailyReturns.reduce((sum, value) => sum + value, 0) /
      dailyReturns.length;
    const variance = dailyReturns.reduce(
      (sum, value) => sum + (value - average) ** 2,
      0,
    ) / (dailyReturns.length - 1);
    const annualizedVolatility = Math.sqrt(variance) *
      Math.sqrt(TRADING_DAYS_PER_YEAR);
    if (Number.isFinite(annualizedVolatility) && annualizedVolatility > 0) {
      sharpe = (annualizedReturn - STAGE_RISK_FREE_RATE) /
        annualizedVolatility;
    }
  }

  let peak = rows[0].index;
  let maxDrawdown = 0;
  rows.forEach((row) => {
    peak = Math.max(peak, row.index);
    maxDrawdown = Math.min(maxDrawdown, row.index / peak - 1);
  });
  const calmar = maxDrawdown < -1e-10
    ? annualizedReturn / Math.abs(maxDrawdown)
    : null;
  return {
    sharpe: Number.isFinite(sharpe) ? sharpe : null,
    calmar: Number.isFinite(calmar) ? calmar : null,
  };
}

function formatRatio(value) {
  return Number.isFinite(value) ? Number(value).toFixed(2) : "—";
}

function createRiskRatioValue(value, isAnnualPeriod) {
  const element = document.createElement("strong");
  element.className = "risk-ratio-value";
  element.textContent = formatRatio(value);
  if (!isAnnualPeriod) {
    element.classList.add("not-applicable");
    element.title = "仅统计近1年、近3年和近5年";
    return element;
  }
  if (!Number.isFinite(value)) {
    element.title = "净值数据不足或无法形成有效比率";
    return element;
  }

  const rating = value >= 2
    ? { className: "excellent", label: "优秀" }
    : value >= 1
      ? { className: "good", label: "良好" }
      : null;
  if (rating) {
    element.classList.add(`is-${rating.className}`);
    const badge = document.createElement("small");
    badge.className = "risk-ratio-badge";
    badge.textContent = rating.label;
    element.append(badge);
  }
  return element;
}

function renderPerformance(performance) {
  currentPerformance = performance ?? {};
  const chart = document.querySelector("#performance-chart");
  const periods = [
    { label: "近1天", key: "日涨幅" },
    { label: "近1月", key: "近1月" },
    { label: "近3月", key: "近3月" },
    { label: "近6月", key: "近6月" },
    { label: "今年以来", key: "今年以来" },
    { label: "近1年", key: "近1年" },
    { label: "近3年", key: "近3年" },
    { label: "近5年", key: "近5年" },
    { label: "成立以来", key: "成立以来" },
  ];
  chart.replaceChildren();
  const benchmarkHeading = currentTrackBenchmark?.简称
    ? `${currentTrackBenchmark.简称}涨幅`
    : "赛道涨幅";
  text(
    "#stage-benchmark-heading",
    benchmarkHeading,
  );

  periods.forEach(({ label: period, key }, index) => {
    const rawValue = currentPerformance[key];
    let numeric = optionalNumber(rawValue);
    if (numeric == null && key === "近5年") {
      const rows = stageRiskIndexRows(key);
      const hasFullFiveYears = rows.length >= 2 &&
        daysBetween(rows[0].date, rows.at(-1).date) >= 365 * 5 - 14;
      if (hasFullFiveYears) {
        numeric = (rows.at(-1).index / rows[0].index - 1) * 100;
      }
    }
    const valid = numeric != null;
    const item = document.createElement("div");
    const direction =
      !valid || numeric === 0 ? "neutral" : numeric > 0 ? "positive" : "negative";
    item.className = `stage-performance-row ${direction}`;
    item.style.animationDelay = `${index * 55}ms`;

    const label = document.createElement("span");
    label.className = "stage-period";
    label.textContent = period;

    const value = document.createElement("strong");
    value.dataset.label = "基金涨幅";
    value.textContent = valid ? formatPercent(numeric) : "—";
    value.className = valid ? movementClass(numeric) : "";

    const benchmarkReturn = benchmarkStageReturn(key);
    const benchmarkValue = document.createElement("strong");
    benchmarkValue.dataset.label = benchmarkHeading;
    benchmarkValue.className = `benchmark-value ${
      Number.isFinite(benchmarkReturn)
        ? movementClass(benchmarkReturn)
        : ""
    }`;
    benchmarkValue.textContent = Number.isFinite(benchmarkReturn)
      ? formatPercent(benchmarkReturn)
      : "—";

    const relativeReturn = Number.isFinite(numeric) &&
      Number.isFinite(benchmarkReturn)
      ? numeric - benchmarkReturn
      : null;
    const relativeValue = document.createElement("strong");
    relativeValue.dataset.label = "相对赛道";
    relativeValue.className = `relative-value ${
      Number.isFinite(relativeReturn) ? movementClass(relativeReturn) : ""
    }`;
    relativeValue.textContent = Number.isFinite(relativeReturn)
      ? `${relativeReturn > 0 ? "+" : ""}${relativeReturn.toFixed(2)}pp`
      : "—";

    const isAnnualRiskPeriod = ANNUAL_RISK_PERIOD_KEYS.has(key);
    const riskMetrics = valid && isAnnualRiskPeriod
      ? calculateStageRiskMetrics(key)
      : { sharpe: null, calmar: null };
    const sharpeValue = createRiskRatioValue(
      riskMetrics.sharpe,
      isAnnualRiskPeriod,
    );
    const calmarValue = createRiskRatioValue(
      riskMetrics.calmar,
      isAnnualRiskPeriod,
    );
    sharpeValue.dataset.label = "夏普比率";
    calmarValue.dataset.label = "卡玛比率";

    item.append(
      label,
      value,
      benchmarkValue,
      relativeValue,
      sharpeValue,
      calmarValue,
    );
    chart.append(item);
  });
}

function computePeriodicReturns(unit) {
  const rows = (currentNavHistory?.累计净值?.明细 ?? [])
    .map((row) => ({
      日期: row.日期,
      value: Number(row.累计净值),
    }))
    .filter((row) => row.日期 && Number.isFinite(row.value))
    .sort((a, b) => a.日期.localeCompare(b.日期));
  if (rows.length < 2) return [];

  const keyOf = (isoDate) => {
    if (unit === "year") return isoDate.slice(0, 4);
    if (unit === "quarter") {
      const year = isoDate.slice(0, 4);
      const quarter = Math.ceil(Number(isoDate.slice(5, 7)) / 3);
      return `${year}-Q${quarter}`;
    }
    return isoDate.slice(0, 7);
  };

  // 每个自然周期保留首末净值点。
  const buckets = new Map();
  rows.forEach((row) => {
    const key = keyOf(row.日期);
    const bucket = buckets.get(key);
    if (!bucket) {
      buckets.set(key, { key, first: row, last: row });
    } else {
      bucket.last = row;
    }
  });

  const ordered = [...buckets.values()].sort((a, b) =>
    a.key.localeCompare(b.key),
  );
  return ordered.map((bucket, index) => {
    // 以上一周期期末净值为基准，衔接跨期涨跌；首个周期回退到本周期期初。
    const base =
      index > 0 ? ordered[index - 1].last.value : bucket.first.value;
    const change =
      Number.isFinite(base) && base !== 0
        ? (bucket.last.value / base - 1) * 100
        : null;
    return {
      key: bucket.key,
      label:
        unit === "year"
          ? `${bucket.key}年`
          : unit === "quarter"
            ? `${bucket.key.slice(0, 4)} Q${bucket.key.at(-1)}`
          : `${bucket.key.slice(0, 4)}/${bucket.key.slice(5, 7)}`,
      change,
      partial: index === 0,
      startDate:
        index > 0
          ? ordered[index - 1].last.日期
          : bucket.first.日期,
      endDate: bucket.last.日期,
    };
  });
}

function renderPeriodicReturns(unit = currentPeriodicUnit) {
  currentPeriodicUnit = unit;
  const list = document.querySelector("#periodic-returns-grid");
  const empty = document.querySelector("#periodic-returns-empty");
  list.replaceChildren();

  document.querySelectorAll("[data-periodic-unit]").forEach((button) => {
    const active = button.dataset.periodicUnit === unit;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  text(
    "#periodic-returns-subtitle",
    unit === "year"
      ? "各自然年内的基金、赛道与相对涨跌幅"
      : unit === "quarter"
        ? "各自然季度内的基金、赛道与相对涨跌幅"
        : "各自然月内的基金、赛道与相对涨跌幅",
  );
  text(
    "#periodic-benchmark-heading",
    currentTrackBenchmark?.简称
      ? `${currentTrackBenchmark.简称}涨幅`
      : "赛道涨幅",
  );

  let entries = computePeriodicReturns(unit);
  if (unit === "month") entries = entries.slice(-24);

  if (!entries.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  entries
    .slice()
    .reverse()
    .forEach((entry, index) => {
      const numeric = entry.change;
      const valid = Number.isFinite(numeric);
      const direction =
        !valid || numeric === 0
          ? "neutral"
          : numeric > 0
            ? "positive"
            : "negative";
      const item = document.createElement("div");
      item.className = `periodic-return-row ${direction}`;
      item.style.animationDelay = `${Math.min(index * 40, 480)}ms`;

      const label = document.createElement("span");
      label.textContent = entry.label;

      const value = document.createElement("strong");
      value.textContent = valid ? formatPercent(numeric) : "—";
      value.className = valid ? movementClass(numeric) : "";

      const benchmarkReturn = benchmarkReturnBetween(
        entry.startDate,
        entry.endDate,
      );
      const benchmarkValue = document.createElement("strong");
      benchmarkValue.className = `benchmark-value ${
        Number.isFinite(benchmarkReturn)
          ? movementClass(benchmarkReturn)
          : ""
      }`;
      benchmarkValue.textContent = Number.isFinite(benchmarkReturn)
        ? formatPercent(benchmarkReturn)
        : "—";

      const relativeReturn = valid && Number.isFinite(benchmarkReturn)
        ? numeric - benchmarkReturn
        : null;
      const relative = document.createElement("strong");
      relative.className = `relative-value ${
        Number.isFinite(relativeReturn) ? movementClass(relativeReturn) : ""
      }`;
      relative.textContent = Number.isFinite(relativeReturn)
        ? `${relativeReturn > 0 ? "+" : ""}${relativeReturn.toFixed(2)}pp`
        : "—";

      item.append(label, value, benchmarkValue, relative);
      if (entry.partial) {
        item.title = `${entry.label}为区间起点，涨跌幅以本期首个净值为基准。`;
      }
      list.append(item);
    });
}

function svgNode(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => {
    node.setAttribute(key, value);
  });
  return node;
}

function formatChartDate(value, includeYear = true) {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("zh-CN", {
    year: includeYear ? "numeric" : undefined,
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function filterNavRows(rows, range) {
  if (!rows.length || range === "all") return rows;
  const latest = new Date(
    `${rows[rows.length - 1].日期}T00:00:00`,
  );
  const cutoff = new Date(latest);
  if (range === "1m") cutoff.setMonth(cutoff.getMonth() - 1);
  if (range === "3m") cutoff.setMonth(cutoff.getMonth() - 3);
  if (range === "6m") cutoff.setMonth(cutoff.getMonth() - 6);
  if (range === "1y") cutoff.setFullYear(cutoff.getFullYear() - 1);
  if (range === "3y") cutoff.setFullYear(cutoff.getFullYear() - 3);
  if (range === "5y") cutoff.setFullYear(cutoff.getFullYear() - 5);
  return rows.filter(
    (point) => new Date(`${point.日期}T00:00:00`) >= cutoff,
  );
}

function filterCustomRows(rows) {
  if (!currentCustomRange.start || !currentCustomRange.end) return [];
  return rows.filter(
    (point) =>
      point.日期 >= currentCustomRange.start &&
      point.日期 <= currentCustomRange.end,
  );
}

function customReturnRows() {
  const returnRanges = currentNavHistory?.累计收益率?.区间 ?? {};
  const totalReturnRows =
    ["1m", "3m", "6m", "1y", "3y", "5y", "all"]
      .map((range) => returnRanges[range] ?? [])
      .find(
        (rows) =>
          rows.length >= 2 &&
          rows[0].日期 <= currentCustomRange.start &&
          rows.at(-1).日期 >= currentCustomRange.end,
      ) ?? returnRanges.all ?? [];
  const selectedReturns = filterCustomRows(totalReturnRows);
  if (selectedReturns.length >= 2) {
    const baseReturn = Number(selectedReturns[0].累计收益率);
    const baseIndex = 1 + baseReturn / 100;
    if (Number.isFinite(baseIndex) && baseIndex > 0) {
      return selectedReturns.map((row) => ({
        日期: row.日期,
        累计收益率:
          ((1 + Number(row.累计收益率) / 100) / baseIndex - 1) * 100,
      }));
    }
  }

  const cumulativeRows = filterCustomRows(
    currentNavHistory?.累计净值?.明细 ?? [],
  );
  if (cumulativeRows.length < 2) return [];
  const baseNav = Number(cumulativeRows[0].累计净值);
  if (!Number.isFinite(baseNav) || baseNav <= 0) return [];
  return cumulativeRows.map((row) => ({
    日期: row.日期,
    累计收益率: (Number(row.累计净值) / baseNav - 1) * 100,
  }));
}

function daysBetween(start, end) {
  const startTime = new Date(`${start}T00:00:00Z`).getTime();
  const endTime = new Date(`${end}T00:00:00Z`).getTime();
  return Math.max(0, Math.round((endTime - startTime) / 86400000));
}

function analyzeDrawdownRows(returnRows) {
  const selected = returnRows
    .map((row) => ({
      日期: row.日期,
      累计收益率: Number(row.累计收益率),
    }))
    .filter(
      (row) => row.日期 && Number.isFinite(row.累计收益率),
    )
    .sort((a, b) => a.日期.localeCompare(b.日期));

  if (!selected.length) {
    return {
      rows: [],
      maxDrawdown: 0,
      peakIndex: null,
      troughIndex: null,
      recoveryIndex: null,
      recoveryDays: null,
      elapsedRecoveryDays: null,
    };
  }

  let runningPeak = 1 + selected[0].累计收益率 / 100;
  let runningPeakIndex = 0;
  let maxDrawdown = 0;
  let maxPeakIndex = 0;
  let troughIndex = 0;
  let maxPeakValue = runningPeak;

  const rows = selected.map((row, index) => {
    const returnIndex = 1 + row.累计收益率 / 100;
    if (returnIndex > runningPeak) {
      runningPeak = returnIndex;
      runningPeakIndex = index;
    }
    const drawdown =
      runningPeak > 0 ? (returnIndex / runningPeak - 1) * 100 : 0;
    if (drawdown < maxDrawdown) {
      maxDrawdown = drawdown;
      maxPeakIndex = runningPeakIndex;
      troughIndex = index;
      maxPeakValue = runningPeak;
    }
    return {
      ...row,
      收益指数: returnIndex,
      回撤: drawdown,
    };
  });

  let recoveryIndex = null;
  if (maxDrawdown < -0.000001) {
    recoveryIndex = rows.findIndex(
      (row, index) =>
        index > troughIndex && row.收益指数 >= maxPeakValue * (1 - 1e-10),
    );
    if (recoveryIndex < 0) recoveryIndex = null;
  }

  const recoveryDays =
    recoveryIndex === null
      ? null
      : daysBetween(rows[troughIndex].日期, rows[recoveryIndex].日期);
  const elapsedRecoveryDays =
    maxDrawdown < -0.000001 && recoveryIndex === null
      ? daysBetween(rows[troughIndex].日期, rows.at(-1).日期)
      : null;

  return {
    rows,
    maxDrawdown,
    peakIndex: maxPeakIndex,
    troughIndex,
    recoveryIndex,
    recoveryDays,
    elapsedRecoveryDays,
  };
}

function computeDrawdownAnalysis(range) {
  let returnRows =
    range === "custom"
      ? customReturnRows()
      : currentNavHistory?.累计收益率?.区间?.[range] ?? [];

  // 上游偶尔缺少某个收益区间，用单位净值首日归零作为降级数据源。
  if (returnRows.length < 2) {
    const unitRows = currentNavHistory?.单位净值?.明细 ?? [];
    const filtered =
      range === "custom"
        ? filterCustomRows(unitRows)
        : filterNavRows(unitRows, range);
    const baseNav = Number(filtered[0]?.单位净值);
    returnRows =
      Number.isFinite(baseNav) && baseNav > 0
        ? filtered.map((row) => ({
            日期: row.日期,
            累计收益率: (Number(row.单位净值) / baseNav - 1) * 100,
          }))
        : [];
  }

  return analyzeDrawdownRows(returnRows);
}

function computeDrawdownRows(range) {
  return computeDrawdownAnalysis(range).rows;
}

function navRowsFor(metric, range) {
  if (metric === "分红记录") {
    const rows = currentDividends.map((row) => ({
      ...row,
      日期: row.除息日,
    }));
    return range === "custom"
      ? filterCustomRows(rows)
      : filterNavRows(rows, range);
  }
  if (metric === "回撤修复") {
    return computeDrawdownRows(range);
  }
  if (range === "custom") {
    return metric === "累计收益率"
      ? customReturnRows()
      : filterCustomRows(currentNavHistory?.[metric]?.明细 ?? []);
  }
  if (metric === "累计收益率") {
    return currentNavHistory?.累计收益率?.区间?.[range] ?? [];
  }
  return filterNavRows(currentNavHistory?.[metric]?.明细 ?? [], range);
}

function dividendFrequency(rows) {
  const periods = rows
    .map((row) => {
      const matched = /^(\d{4})-(\d{2})-\d{2}$/.exec(row.除息日 ?? "");
      if (!matched) return null;
      return {
        year: Number(matched[1]),
        month: Number(matched[2]),
      };
    })
    .filter(Boolean);
  if (!periods.length) return null;

  const consecutiveTail = (periodKey) => {
    const keys = [...new Set(periods.map(periodKey))].sort((a, b) => a - b);
    let count = 1;
    for (let index = keys.length - 1; index > 0; index -= 1) {
      if (keys[index] - keys[index - 1] !== 1) break;
      count += 1;
    }
    return count;
  };
  const monthlyStreak = consecutiveTail(
    ({ year, month }) => year * 12 + month - 1,
  );
  if (monthlyStreak >= 6) {
    return {
      label: "每月分红",
      title: `最近连续 ${monthlyStreak} 个月均有分红记录`,
    };
  }

  const quarterlyStreak = consecutiveTail(
    ({ year, month }) => year * 4 + Math.floor((month - 1) / 3),
  );
  if (quarterlyStreak >= 4) {
    return {
      label: "每季分红",
      title: `最近连续 ${quarterlyStreak} 个季度均有分红记录`,
    };
  }

  const yearlyStreak = consecutiveTail(({ year }) => year);
  if (yearlyStreak >= 3) {
    return {
      label: "每年分红",
      title: `最近连续 ${yearlyStreak} 年均有分红记录`,
    };
  }
  return null;
}

function renderDividendHistory(rows) {
  const list = document.querySelector("#dividend-history-list");
  const empty = document.querySelector("#no-dividend-history");
  const frequencySummary = document.querySelector("#dividend-frequency");
  const frequencyBadge = document.querySelector("#dividend-frequency-badge");
  const frequency = dividendFrequency(currentDividends);
  const validAmounts = rows
    .map((row) => Number(row.每份分红))
    .filter(Number.isFinite);
  const totalPerShare = validAmounts.reduce(
    (sum, amount) => sum + amount,
    0,
  );
  const latest = rows.at(-1);

  frequencySummary.hidden = !frequency;
  frequencyBadge.textContent = frequency?.label ?? "";
  frequencyBadge.title = frequency?.title ?? "";
  list.replaceChildren();
  empty.hidden = Boolean(rows.length);
  rows
    .slice()
    .reverse()
    .forEach((row, index) => {
      const item = document.createElement("div");
      item.className = "dividend-history-row";
      item.style.setProperty(
        "--dividend-delay",
        `${Math.min(index * 45, 360)}ms`,
      );

      const date = document.createElement("time");
      date.dateTime = row.除息日;
      date.textContent = formatChartDate(row.除息日);

      const amount = document.createElement("strong");
      amount.textContent = Number.isFinite(Number(row.每份分红))
        ? `${formatNumber(row.每份分红, 4)} 元`
        : "金额暂无";

      const description = document.createElement("span");
      description.textContent = row.说明 ?? "现金分红";
      item.append(date, amount, description);
      list.append(item);
    });

  text("#nav-range-change-label", "分红次数");
  text("#nav-range-high-label", "累计每份分红");
  text("#nav-range-low-label", "最近每份分红");
  text("#nav-range-dates-label", "除息日期范围");
  document.querySelector("#nav-range-change").className = "";
  text("#nav-range-change", `${rows.length} 次`);
  text(
    "#nav-range-high",
    validAmounts.length ? `${formatNumber(totalPerShare, 4)} 元` : null,
  );
  text(
    "#nav-range-low",
    latest && Number.isFinite(Number(latest.每份分红))
      ? `${formatNumber(latest.每份分红, 4)} 元`
      : null,
  );
  text(
    "#nav-range-dates",
    rows.length
      ? `${formatChartDate(rows[0].除息日)} — ${formatChartDate(
          rows.at(-1).除息日,
        )}`
      : null,
  );
}

function localIsoDate(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function initializeCustomRange() {
  const sourceRows =
    currentNavHistory?.累计收益率?.区间?.all?.length
      ? currentNavHistory.累计收益率.区间.all
      : currentNavHistory?.累计净值?.明细 ?? [];
  const startInput = document.querySelector("#custom-range-start");
  const endInput = document.querySelector("#custom-range-end");
  if (sourceRows.length < 2) {
    currentCustomRange = { start: "", end: "" };
    startInput.value = "";
    endInput.value = "";
    startInput.removeAttribute("min");
    startInput.removeAttribute("max");
    endInput.removeAttribute("min");
    endInput.removeAttribute("max");
    text("#custom-range-available", "暂无可用日期范围");
    return;
  }

  const firstDate = sourceRows[0].日期;
  const lastDate = sourceRows.at(-1).日期;
  const defaultStart = new Date(`${lastDate}T00:00:00`);
  defaultStart.setFullYear(defaultStart.getFullYear() - 1);
  currentCustomRange = {
    start: localIsoDate(defaultStart) < firstDate
      ? firstDate
      : localIsoDate(defaultStart),
    end: lastDate,
  };
  [startInput, endInput].forEach((input) => {
    input.min = firstDate;
    input.max = lastDate;
  });
  startInput.value = currentCustomRange.start;
  endInput.value = currentCustomRange.end;
  text(
    "#custom-range-available",
    `可用 ${formatChartDate(firstDate)} — ${formatChartDate(lastDate)}`,
  );
}

function showCustomRangeError(message = "") {
  const error = document.querySelector("#custom-range-error");
  error.hidden = !message;
  error.textContent = message;
}

function benchmarkRowsForChart(fundRows) {
  const source = currentTrackBenchmark?.明细 ?? [];
  if (fundRows.length < 2 || source.length < 2) return [];
  const start = fundRows[0].日期;
  const end = fundRows.at(-1).日期;
  const usable = source.filter((row) => row.日期 <= end);
  const baseRow =
    usable.filter((row) => row.日期 <= start).at(-1) ??
    usable.find((row) => row.日期 >= start);
  const baseValue = Number(baseRow?.指数值);
  if (!baseRow || !Number.isFinite(baseValue) || baseValue <= 0) return [];

  const rows = usable
    .filter((row) => row.日期 >= start && row.日期 <= end)
    .map((row) => ({
      日期: row.日期,
      累计收益率: (Number(row.指数值) / baseValue - 1) * 100,
    }))
    .filter((row) => Number.isFinite(row.累计收益率));
  if (baseRow.日期 < start) {
    rows.unshift({ 日期: start, 累计收益率: 0 });
  }
  return rows;
}

function recoveryDurationLabel(analysis) {
  if (!analysis?.rows?.length) return "—";
  if (analysis.maxDrawdown >= -0.000001) return "0 天";
  return analysis.recoveryIndex === null
    ? `修复中 · 已 ${analysis.elapsedRecoveryDays} 天`
    : `${analysis.recoveryDays} 天`;
}

function drawdownAriaDescription(analysis) {
  if (!analysis?.rows?.length) return "暂无";
  const drawdown = Math.abs(analysis.maxDrawdown).toFixed(2);
  if (analysis.maxDrawdown >= -0.000001) {
    return `${drawdown}%，区间内无回撤`;
  }
  return analysis.recoveryIndex === null
    ? `${drawdown}%，尚未修复，已历时${analysis.elapsedRecoveryDays}天`
    : `${drawdown}%，历时${analysis.recoveryDays}天修复`;
}

function positionDrawdownLabels() {
  const layer = document.querySelector("#drawdown-label-layer");
  const svg = document.querySelector("#nav-history-chart");
  if (!layer || !svg || layer.hidden || !layer.children.length) return;

  const layerBounds = layer.getBoundingClientRect();
  const svgBounds = svg.getBoundingClientRect();
  if (!layerBounds.width || !layerBounds.height || !svgBounds.width) return;

  const chartLeft = svgBounds.left - layerBounds.left;
  const chartTop = svgBounds.top - layerBounds.top;
  const edgePadding = 8;
  Array.from(layer.children).forEach((label) => {
    const pointX = chartLeft +
      (Number(label.dataset.chartX) / navChartDimensions.width) * svgBounds.width;
    const pointY = chartTop +
      (Number(label.dataset.chartY) / navChartDimensions.height) * svgBounds.height;
    const labelWidth = label.offsetWidth;
    const labelHeight = label.offsetHeight;
    const left = Math.min(
      chartLeft + svgBounds.width - labelWidth - edgePadding,
      Math.max(chartLeft + edgePadding, pointX - labelWidth / 2),
    );
    const preferredTop = label.dataset.position === "below"
      ? pointY + 12
      : pointY - labelHeight - 12;
    const top = Math.min(
      chartTop + svgBounds.height - labelHeight - edgePadding,
      Math.max(chartTop + edgePadding, preferredTop),
    );
    label.style.left = `${left}px`;
    label.style.top = `${top}px`;
  });
}

function addDrawdownLabel(point, className, label, position) {
  const layer = document.querySelector("#drawdown-label-layer");
  if (!layer) return;
  const labelNode = document.createElement("span");
  labelNode.className = `drawdown-chart-label ${className}`;
  labelNode.dataset.chartX = String(point.x);
  labelNode.dataset.chartY = String(point.y);
  labelNode.dataset.position = position;
  labelNode.textContent = label;
  layer.append(labelNode);
}

function renderDrawdownComparison(fundAnalysis, benchmarkAnalysis) {
  const panel = document.querySelector("#drawdown-comparison");
  const benchmarkName =
    currentTrackBenchmark?.简称 ?? currentTrackBenchmark?.名称 ?? "赛道基准";
  text("#drawdown-fund-heading", "基金");
  text("#drawdown-benchmark-heading", benchmarkName);
  text(
    "#drawdown-fund-value",
    fundAnalysis?.rows?.length
      ? `${Math.abs(fundAnalysis.maxDrawdown).toFixed(2)}%`
      : null,
  );
  text(
    "#drawdown-benchmark-value",
    benchmarkAnalysis?.rows?.length
      ? `${Math.abs(benchmarkAnalysis.maxDrawdown).toFixed(2)}%`
      : null,
  );
  text("#drawdown-fund-recovery", recoveryDurationLabel(fundAnalysis));
  text(
    "#drawdown-benchmark-recovery",
    recoveryDurationLabel(benchmarkAnalysis),
  );
  panel.setAttribute(
    "aria-label",
    `基金最大回撤${drawdownAriaDescription(
      fundAnalysis,
    )}；${benchmarkName}最大回撤${drawdownAriaDescription(
      benchmarkAnalysis,
    )}`,
  );
}

function formatNavValue(value, metric = currentNavMetric, axis = false) {
  if (metric === "累计收益率" || metric === "回撤修复") {
    return axis ? `${Number(value).toFixed(2)}%` : formatPercent(value);
  }
  return formatNumber(value, 4);
}

function buildYAxisTicks(
  minValue,
  maxValue,
  includeZero = false,
  tickCount = 5,
) {
  const intervals = Math.max(tickCount - 1, 1);
  const ticks = Array.from({ length: tickCount }, (_, index) => {
    const ratio = index / intervals;
    return maxValue - ratio * (maxValue - minValue);
  });
  if (includeZero) ticks.push(0);

  return ticks
    .sort((a, b) => b - a)
    .filter(
      (value, index, values) =>
        index === 0 ||
        Math.abs(value - values[index - 1]) >
          Math.max(Math.abs(maxValue - minValue) * 0.000001, 1e-9),
    );
}

// 沪深300 走势独立获取，不受用户当前所选赛道基准影响。
async function ensureHs300Series() {
  if (hs300Series) return hs300Series;
  const cached = trackBenchmarkCache.get("hs300");
  if (cached?.明细?.length) {
    hs300Series = cached.明细;
    return hs300Series;
  }
  const requestId = ++hs300RequestId;
  try {
    const response = await fetch("/api/benchmarks/hs300");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "沪深300 加载失败");
    if (requestId !== hs300RequestId) return hs300Series;
    trackBenchmarkCache.set("hs300", payload);
    hs300Series = payload.明细 ?? [];
  } catch {
    if (requestId === hs300RequestId) hs300Series = null;
  }
  return hs300Series;
}

// 将 [{日期, 值}] 序列按周期起止裁剪并以首个可用点归零为累计涨幅。
function normalizedCycleReturns(rows, start, end, valueKey) {
  if (!rows?.length) return [];
  const within = rows
    .map((row) => ({
      日期: row.日期,
      value: Number(row[valueKey]),
    }))
    .filter(
      (row) =>
        row.日期 &&
        Number.isFinite(row.value) &&
        row.日期 >= start &&
        row.日期 <= end,
    )
    .sort((a, b) => a.日期.localeCompare(b.日期));
  if (within.length < 2) return [];
  const base = within[0].value;
  if (!Number.isFinite(base) || base <= 0) return [];
  return within.map((row) => ({
    日期: row.日期,
    累计收益率: (row.value / base - 1) * 100,
  }));
}

function computeBullBearCycles() {
  const navRows = currentNavHistory?.累计净值?.明细 ?? [];
  const hs300 = hs300Series ?? [];
  if (navRows.length < 2 || hs300.length < 2) return [];

  return bullBearCycles
    .map((cycle) => {
      const fund = normalizedCycleReturns(
        navRows,
        cycle.start,
        cycle.end,
        "累计净值",
      );
      const benchmark = normalizedCycleReturns(
        hs300,
        cycle.start,
        cycle.end,
        "指数值",
      );
      if (fund.length < 2 || benchmark.length < 2) return null;
      return {
        ...cycle,
        fund,
        benchmark,
        fundReturn: fund.at(-1).累计收益率,
        benchmarkReturn: benchmark.at(-1).累计收益率,
      };
    })
    .filter(Boolean);
}

function renderBullBearInfo(cycles) {
  const list = document.querySelector("#bull-bear-info-list");
  list.replaceChildren();
  // 展示的周期只用本基金实际覆盖到的段；用起止日期匹配对应涨幅。
  const coveredKeys = new Set(cycles.map((cycle) => cycle.start));
  bullBearCycles.forEach((cycle) => {
    const covered = cycles.find((item) => item.start === cycle.start);
    const item = document.createElement("div");
    item.className = `bull-bear-info-item ${cycle.type}${
      coveredKeys.has(cycle.start) ? " covered" : ""
    }`;

    const head = document.createElement("div");
    head.className = "bull-bear-info-item-head";
    const name = document.createElement("strong");
    name.textContent = cycle.label;
    const tag = document.createElement("span");
    tag.className = `bull-bear-info-tag ${cycle.type}`;
    tag.textContent = cycle.type === "bull" ? "牛市" : "熊市";
    head.append(name, tag);

    const period = document.createElement("p");
    period.className = "bull-bear-info-period";
    const todayIso = new Date().toISOString().slice(0, 10);
    const endLabel = cycle.end >= todayIso ? "至今" : cycle.end;
    period.textContent = `${cycle.start} 至 ${endLabel} · ${cycle.points}`;

    const driver = document.createElement("p");
    driver.className = "bull-bear-info-driver";
    driver.textContent = cycle.driver;

    item.append(head, period, driver);

    if (covered) {
      const perf = document.createElement("p");
      perf.className = "bull-bear-info-perf";
      perf.textContent = `本基金 ${formatPercent(
        covered.fundReturn,
      )} · 沪深300 ${formatPercent(covered.benchmarkReturn)}`;
      item.append(perf);
    } else {
      const perf = document.createElement("p");
      perf.className = "bull-bear-info-perf muted";
      perf.textContent = "本基金当时尚未成立，未纳入走势图";
      item.append(perf);
    }
    list.append(item);
  });
}

function renderBullBearCycles() {
  const svg = document.querySelector("#bull-bear-chart");
  const empty = document.querySelector("#bull-bear-empty");
  svg.replaceChildren();

  const cycles = computeBullBearCycles();
  renderBullBearInfo(cycles);
  if (!cycles.length) {
    svg.hidden = true;
    empty.hidden = false;
    return;
  }
  svg.hidden = false;
  empty.hidden = true;

  const width = 1000;
  const height = 360;
  const margin = { top: 30, right: 16, bottom: 58, left: 16 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const gap = 10;
  const segmentWidth =
    (plotWidth - gap * (cycles.length - 1)) / cycles.length;

  // 统一 y 轴范围，覆盖所有周期内两条曲线的极值，并含 0。
  let minValue = 0;
  let maxValue = 0;
  cycles.forEach((cycle) => {
    [...cycle.fund, ...cycle.benchmark].forEach((row) => {
      minValue = Math.min(minValue, row.累计收益率);
      maxValue = Math.max(maxValue, row.累计收益率);
    });
  });
  const span = maxValue - minValue || 1;
  minValue -= span * 0.08;
  maxValue += span * 0.08;

  const yFor = (value) =>
    margin.top +
    ((maxValue - value) / Math.max(maxValue - minValue, 0.0001)) * plotHeight;

  // 零基准线。
  const zeroY = yFor(0);
  svg.append(
    svgNode("line", {
      x1: margin.left,
      y1: zeroY,
      x2: width - margin.right,
      y2: zeroY,
      class: "bull-bear-zero",
    }),
  );

  cycles.forEach((cycle, index) => {
    const segLeft = margin.left + index * (segmentWidth + gap);
    const segRight = segLeft + segmentWidth;
    const startT = new Date(`${cycle.start}T00:00:00`).getTime();
    const endT = new Date(`${cycle.end}T00:00:00`).getTime();
    const xFor = (date) =>
      segLeft +
      ((new Date(`${date}T00:00:00`).getTime() - startT) /
        Math.max(endT - startT, 1)) *
        segmentWidth;

    // 周期背景色：牛市浅金、熊市浅灰。
    svg.append(
      svgNode("rect", {
        x: segLeft,
        y: margin.top,
        width: segmentWidth,
        height: plotHeight,
        class: `bull-bear-band ${cycle.type}`,
      }),
    );

    const pathFor = (rows) =>
      rows
        .map(
          (row, i) =>
            `${i === 0 ? "M" : "L"}${xFor(row.日期).toFixed(2)} ${yFor(
              row.累计收益率,
            ).toFixed(2)}`,
        )
        .join(" ");

    svg.append(
      svgNode("path", {
        d: pathFor(cycle.benchmark),
        class: "bull-bear-line benchmark",
      }),
    );
    svg.append(
      svgNode("path", {
        d: pathFor(cycle.fund),
        class: "bull-bear-line fund",
      }),
    );

    // 周期名称。
    const nameLabel = svgNode("text", {
      x: (segLeft + segRight) / 2,
      y: height - margin.bottom + 20,
      class: "bull-bear-name",
      "text-anchor": "middle",
    });
    nameLabel.textContent = cycle.label;
    svg.append(nameLabel);

    // 牛/熊标签。
    const typeLabel = svgNode("text", {
      x: (segLeft + segRight) / 2,
      y: height - margin.bottom + 36,
      class: `bull-bear-type ${cycle.type}`,
      "text-anchor": "middle",
    });
    typeLabel.textContent = cycle.type === "bull" ? "牛市" : "熊市";
    svg.append(typeLabel);

    // 本基金与沪深300 期末涨幅数值。
    const fundEnd = svgNode("text", {
      x: (segLeft + segRight) / 2,
      y: margin.top - 14,
      class: "bull-bear-value fund",
      "text-anchor": "middle",
    });
    fundEnd.textContent = formatPercent(cycle.fundReturn);
    const benchEnd = svgNode("text", {
      x: (segLeft + segRight) / 2,
      y: margin.top - 3,
      class: "bull-bear-value benchmark",
      "text-anchor": "middle",
    });
    benchEnd.textContent = formatPercent(cycle.benchmarkReturn);
    svg.append(fundEnd, benchEnd);
  });
}

function renderNavChart(
  range = currentNavRange,
  metric = currentNavMetric,
) {
  currentNavRange = range;
  currentNavMetric = metric;
  const config = navMetricConfig[metric];
  const customPanel = document.querySelector("#nav-custom-range");
  const svg = document.querySelector("#nav-history-chart");
  const chartShell = document.querySelector("#nav-chart-shell");
  const dividendPanel = document.querySelector("#dividend-history-panel");
  const periodicPanel = document.querySelector("#periodic-returns-panel");
  const stagePanel = document.querySelector("#stage-performance-panel");
  const drawdownComparison = document.querySelector(
    "#drawdown-comparison",
  );
  const bullBearPanel = document.querySelector("#bull-bear-panel");
  const noData = document.querySelector("#no-nav-history");
  const tooltip = document.querySelector("#nav-chart-tooltip");
  const drawdownLabelLayer = document.querySelector(
    "#drawdown-label-layer",
  );
  const summary = document.querySelector(".nav-history-summary");
  const isDrawdownView = metric === "回撤修复";
  const isBullBearView = metric === "牛熊周期";
  const isPerformanceView = metric === "累计收益率";
  const isBenchmarkCurveView = isPerformanceView || isDrawdownView;
  const drawdownAnalysis = isDrawdownView
    ? computeDrawdownAnalysis(range)
    : null;
  const rows = drawdownAnalysis?.rows ?? navRowsFor(metric, range);
  const values = rows
    .map((row) => Number(row[config.valueKey]))
    .filter(Number.isFinite);
  svg.replaceChildren();
  drawdownLabelLayer.replaceChildren();
  drawdownLabelLayer.hidden = !isDrawdownView;
  svg.classList.toggle("drawdown-view", isDrawdownView);
  tooltip.hidden = true;
  navPlotPoints = [];
  benchmarkPlotPoints = [];
  const isDividendView = metric === "分红记录";
  const isPeriodicView = metric === "周期收益";
  const isStageView = metric === "阶段收益";
  const isPanelView =
    isDividendView || isPeriodicView || isStageView || isBullBearView;
  customPanel.hidden = range !== "custom" || isPanelView;
  chartShell.hidden = isPanelView;
  dividendPanel.hidden = !isDividendView;
  periodicPanel.hidden = !isPeriodicView;
  stagePanel.hidden = !isStageView;
  bullBearPanel.hidden = !isBullBearView;
  drawdownComparison.hidden = !isDrawdownView;
  summary.hidden = isPeriodicView || isStageView || isDrawdownView || isBullBearView;
  summary.classList.toggle("drawdown-summary", isDrawdownView);
  document.querySelector("#nav-range-switcher").hidden =
    isPeriodicView || isStageView || isBullBearView;
  document.querySelector("#track-benchmark-control").hidden = isBullBearView;
  document.querySelector("#nav-chart-legend").hidden =
    !isBenchmarkCurveView;
  text(
    "#nav-chart-fund-legend",
    isDrawdownView ? "基金回撤阶段" : "基金涨幅",
  );
  text(
    "#benchmark-legend-label",
    isDrawdownView
      ? `${currentTrackBenchmark?.简称 ?? "赛道基准"}回撤阶段`
      : currentTrackBenchmark?.简称 ?? "赛道基准",
  );

  document.querySelectorAll("[data-nav-range]").forEach((button) => {
    const active = button.dataset.navRange === range;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-nav-metric]").forEach((button) => {
    const active = button.dataset.navMetric === metric;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  text(
    "#nav-chart-subtitle",
    range === "custom" && !isPeriodicView && !isStageView
      ? `自定义区间 · ${config.subtitle}`
      : config.subtitle,
  );
  text("#nav-chart-note", config.note);
  if (isBullBearView) {
    noData.hidden = true;
    ensureHs300Series().then(() => {
      if (currentNavMetric === "牛熊周期") renderBullBearCycles();
    });
    return;
  }
  if (isStageView) {
    noData.hidden = true;
    renderPerformance(currentPerformance);
    return;
  }
  if (isPeriodicView) {
    noData.hidden = true;
    renderPeriodicReturns(currentPeriodicUnit);
    return;
  }
  if (isDividendView) {
    noData.hidden = true;
    if (range === "custom") showCustomRangeError();
    renderDividendHistory(rows);
    return;
  }
  text(
    "#nav-range-change-label",
    isDrawdownView
      ? "最大回撤比例"
      : isPerformanceView
        ? "基金涨幅"
        : "首末变化",
  );
  text(
    "#nav-range-dates-label",
    isDrawdownView ? "回撤修复阶段" : "覆盖日期",
  );
  text(
    "#nav-range-high-label",
    isDrawdownView
      ? "最大回撤修复天数"
      : isPerformanceView
        ? "赛道涨幅"
        : "区间最高",
  );
  text(
    "#nav-range-low-label",
    isDrawdownView
      ? "最大回撤阶段"
      : isPerformanceView
        ? "相对赛道"
        : "区间最低",
  );

  if (rows.length < 2 || values.length < 2) {
    noData.hidden = false;
    if (range === "custom") {
      showCustomRangeError(
        "所选日期内不足两个有效净值点，请扩大时间范围。",
      );
    }
    text("#nav-range-change", "—");
    text("#nav-range-high", "—");
    text("#nav-range-low", "—");
    text("#nav-range-dates", "—");
    if (isDrawdownView) {
      renderDrawdownComparison(drawdownAnalysis, null);
    }
    return;
  }

  noData.hidden = true;
  if (range === "custom") showCustomRangeError();
  const isMobileChart = window.matchMedia("(max-width: 700px)").matches;
  const width = isMobileChart ? 360 : 1000;
  const height = isMobileChart ? 320 : 360;
  const margin = isMobileChart
    ? { top: 22, right: 12, bottom: 50, left: 58 }
    : { top: 24, right: 22, bottom: 46, left: 68 };
  const xTickCount = isMobileChart ? 3 : 5;
  const yTickCount = isMobileChart ? 3 : 5;
  navChartDimensions = { width, height };
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.classList.toggle("mobile-chart", isMobileChart);
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const startTime = new Date(`${rows[0].日期}T00:00:00`).getTime();
  const endTime = new Date(`${rows[rows.length - 1].日期}T00:00:00`).getTime();
  const isPercentageChart =
    metric === "累计收益率" || metric === "回撤修复";
  const rawBenchmarkRows = isBenchmarkCurveView
    ? benchmarkRowsForChart(rows)
    : [];
  const benchmarkDrawdownAnalysis = isDrawdownView
    ? analyzeDrawdownRows(rawBenchmarkRows)
    : null;
  const benchmarkRows = isDrawdownView
    ? benchmarkDrawdownAnalysis.rows
    : rawBenchmarkRows;
  if (isDrawdownView) {
    renderDrawdownComparison(
      drawdownAnalysis,
      benchmarkDrawdownAnalysis,
    );
  }
  const benchmarkValues = benchmarkRows.map((row) => row.累计收益率);
  let minValue = Math.min(...values);
  let maxValue = Math.max(...values);
  if (benchmarkValues.length) {
    minValue = Math.min(minValue, ...benchmarkValues);
    maxValue = Math.max(maxValue, ...benchmarkValues);
  }
  if (isPercentageChart) {
    minValue = Math.min(minValue, 0);
    maxValue = Math.max(maxValue, 0);
  }
  const valueSpan = maxValue - minValue || Math.max(maxValue * 0.02, 0.02);
  minValue = isPercentageChart && minValue === 0
    ? 0
    : minValue - valueSpan * 0.1;
  maxValue = isPercentageChart && maxValue === 0
    ? 0
    : maxValue + valueSpan * 0.1;

  const xFor = (date) =>
    margin.left +
    ((new Date(`${date}T00:00:00`).getTime() - startTime) /
      Math.max(endTime - startTime, 1)) *
      plotWidth;
  const yFor = (value) =>
    margin.top +
    ((maxValue - Number(value)) / Math.max(maxValue - minValue, 0.0001)) *
      plotHeight;

  const defs = svgNode("defs");
  const gradient = svgNode("linearGradient", {
    id: "nav-area-gradient",
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1",
  });
  gradient.append(
    svgNode("stop", {
      offset: "0%",
      "stop-color": "#d33b28",
      "stop-opacity": "0.24",
    }),
    svgNode("stop", {
      offset: "100%",
      "stop-color": "#d33b28",
      "stop-opacity": "0",
    }),
  );
  defs.append(gradient);
  svg.append(defs);

  if (
    isDrawdownView &&
    drawdownAnalysis?.peakIndex !== null &&
    drawdownAnalysis?.troughIndex !== null &&
    drawdownAnalysis.maxDrawdown < -0.000001
  ) {
    const peakDate = rows[drawdownAnalysis.peakIndex].日期;
    const troughDate = rows[drawdownAnalysis.troughIndex].日期;
    const repairEndIndex =
      drawdownAnalysis.recoveryIndex ?? rows.length - 1;
    const repairEndDate = rows[repairEndIndex].日期;
    const phaseBands = svgNode("g", {
      class: "drawdown-phase-bands",
      "aria-hidden": "true",
    });
    const declineStart = xFor(peakDate);
    const declineEnd = xFor(troughDate);
    const repairStart = declineEnd;
    const repairEnd = xFor(repairEndDate);
    phaseBands.append(
      svgNode("rect", {
        x: declineStart,
        y: margin.top,
        width: Math.max(declineEnd - declineStart, 1),
        height: plotHeight,
        class: "drawdown-decline-band",
      }),
      svgNode("rect", {
        x: repairStart,
        y: margin.top,
        width: Math.max(repairEnd - repairStart, 1),
        height: plotHeight,
        class: "drawdown-recovery-band",
      }),
    );
    svg.append(phaseBands);
  }

  const grid = svgNode("g", { class: "nav-grid" });
  const yAxisTicks = buildYAxisTicks(
    minValue,
    maxValue,
    isPercentageChart,
    yTickCount,
  );
  yAxisTicks.forEach((labelValue) => {
    const y = yFor(labelValue);
    const isZeroTick = isPercentageChart && Math.abs(labelValue) < 1e-9;
    grid.append(
      svgNode("line", {
        x1: margin.left,
        y1: y,
        x2: width - margin.right,
        y2: y,
        class: isZeroTick ? "zero-line" : "",
      }),
    );
    const label = svgNode("text", {
      x: margin.left - 12,
      y: y + 4,
      "text-anchor": "end",
      class: isZeroTick ? "zero-label" : "",
    });
    label.textContent = isZeroTick
      ? "0.00%"
      : formatNavValue(labelValue, metric, true);
    grid.append(label);
  });
  for (let index = 0; index < xTickCount; index += 1) {
    const ratio = index / Math.max(xTickCount - 1, 1);
    const time = startTime + ratio * (endTime - startTime);
    const x = margin.left + ratio * plotWidth;
    grid.append(
      svgNode("line", {
        x1: x,
        y1: margin.top,
        x2: x,
        y2: height - margin.bottom,
      }),
    );
    const label = svgNode("text", {
      x,
      y: height - 16,
      "text-anchor":
        index === 0 ? "start" : index === xTickCount - 1 ? "end" : "middle",
    });
    label.textContent = formatChartDate(
      localIsoDate(new Date(time)),
      range !== "1m",
    );
    grid.append(label);
  }
  svg.append(grid);

  navPlotPoints = rows.map((row) => ({
    ...row,
    x: xFor(row.日期),
    y: yFor(row[config.valueKey]),
    value: Number(row[config.valueKey]),
  }));
  const linePath = navPlotPoints
    .map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L${navPlotPoints.at(-1).x.toFixed(2)},${(
    height - margin.bottom
  ).toFixed(2)} L${navPlotPoints[0].x.toFixed(2)},${(
    height - margin.bottom
  ).toFixed(2)} Z`;
  svg.append(
    svgNode("path", { d: areaPath, class: "nav-area" }),
    svgNode("path", { d: linePath, class: "nav-line" }),
  );

  if (benchmarkRows.length >= 2) {
    benchmarkPlotPoints = benchmarkRows.map((row) => ({
      ...row,
      x: xFor(row.日期),
      y: yFor(row.累计收益率),
      value: Number(row.累计收益率),
    }));
    const benchmarkPath = benchmarkPlotPoints
      .map(
        (point, index) =>
          `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`,
      )
      .join(" ");
    svg.append(
      svgNode("path", {
        d: benchmarkPath,
        class: "benchmark-line",
      }),
    );
  }

  if (
    isDrawdownView &&
    drawdownAnalysis?.peakIndex !== null &&
    drawdownAnalysis?.troughIndex !== null &&
    drawdownAnalysis.maxDrawdown < -0.000001
  ) {
    const {
      peakIndex,
      troughIndex,
      recoveryIndex,
      recoveryDays,
      elapsedRecoveryDays,
      maxDrawdown,
    } = drawdownAnalysis;
    const repairEndIndex = recoveryIndex ?? navPlotPoints.length - 1;
    const stages = svgNode("g", { class: "drawdown-stages" });
    const segmentPath = (startIndex, endIndex) =>
      navPlotPoints
        .slice(startIndex, endIndex + 1)
        .map(
          (point, index) =>
            `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`,
        )
        .join(" ");
    stages.append(
      svgNode("path", {
        d: segmentPath(peakIndex, troughIndex),
        class: "drawdown-decline-line",
      }),
      svgNode("path", {
        d: segmentPath(troughIndex, repairEndIndex),
        class: recoveryIndex === null
          ? "drawdown-recovery-line pending"
          : "drawdown-recovery-line",
      }),
    );

    const addMarker = (point, className, label, position = "above") => {
      const marker = svgNode("g", { class: `drawdown-marker ${className}` });
      marker.append(
        svgNode("line", {
          x1: point.x,
          y1: point.y,
          x2: point.x,
          y2: point.y + (position === "below" ? 16 : -16),
        }),
        svgNode("circle", { cx: point.x, cy: point.y, r: 5 }),
      );
      stages.append(marker);
      addDrawdownLabel(point, className, label, position);
    };

    addMarker(
      navPlotPoints[troughIndex],
      "maximum",
      `最大回撤 ${Math.abs(maxDrawdown).toFixed(2)}%`,
      "below",
    );
    addMarker(
      navPlotPoints[repairEndIndex],
      recoveryIndex === null ? "repair pending" : "repair",
      recoveryIndex === null
        ? `修复中 · 已 ${elapsedRecoveryDays} 天`
        : `${recoveryDays} 天修复`,
      "above",
    );
    svg.append(stages);
    requestAnimationFrame(positionDrawdownLabels);
  }

  if (
    isDrawdownView &&
    benchmarkDrawdownAnalysis?.peakIndex !== null &&
    benchmarkDrawdownAnalysis?.troughIndex !== null &&
    benchmarkDrawdownAnalysis.maxDrawdown < -0.000001 &&
    benchmarkPlotPoints.length
  ) {
    const {
      peakIndex,
      troughIndex,
      recoveryIndex,
    } = benchmarkDrawdownAnalysis;
    const repairEndIndex =
      recoveryIndex ?? benchmarkPlotPoints.length - 1;
    const benchmarkStages = svgNode("g", {
      class: "benchmark-drawdown-stages",
    });
    const benchmarkSegmentPath = (startIndex, endIndex) =>
      benchmarkPlotPoints
        .slice(startIndex, endIndex + 1)
        .map(
          (point, index) =>
            `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`,
        )
        .join(" ");
    benchmarkStages.append(
      svgNode("path", {
        d: benchmarkSegmentPath(peakIndex, troughIndex),
        class: "benchmark-drawdown-decline-line",
      }),
      svgNode("path", {
        d: benchmarkSegmentPath(troughIndex, repairEndIndex),
        class:
          recoveryIndex === null
            ? "benchmark-drawdown-recovery-line pending"
            : "benchmark-drawdown-recovery-line",
      }),
    );
    svg.append(benchmarkStages);
  }

  const crosshair = svgNode("g", {
    id: "nav-crosshair",
    class: "nav-crosshair",
    visibility: "hidden",
  });
  crosshair.append(
    svgNode("line", {
      x1: "0",
      y1: margin.top,
      x2: "0",
      y2: height - margin.bottom,
    }),
    svgNode("circle", { cx: "0", cy: "0", r: "5" }),
    svgNode("circle", {
      cx: "0",
      cy: "0",
      r: "4.5",
      class: "benchmark-crosshair-point",
      visibility: "hidden",
    }),
  );
  svg.append(crosshair);

  const firstValue = Number(rows[0][config.valueKey]);
  const lastValue = Number(rows.at(-1)[config.valueKey]);
  const changeElement = document.querySelector("#nav-range-change");
  if (isDrawdownView) {
    const {
      maxDrawdown,
      peakIndex,
      troughIndex,
      recoveryIndex,
      recoveryDays,
      elapsedRecoveryDays,
    } = drawdownAnalysis;
    const hasDrawdown = maxDrawdown < -0.000001;
    changeElement.textContent = `${Math.abs(maxDrawdown).toFixed(2)}%`;
    changeElement.className = hasDrawdown ? "drawdown-value" : "";
    text(
      "#nav-range-high",
      hasDrawdown
        ? recoveryIndex === null
          ? `修复中 · 已 ${elapsedRecoveryDays} 天`
          : `${recoveryDays} 天`
        : "0 天",
    );
    text(
      "#nav-range-low",
      hasDrawdown
        ? `${formatChartDate(rows[peakIndex].日期)} — ${formatChartDate(
            rows[troughIndex].日期,
          )}`
        : "区间内无回撤",
    );
    text(
      "#nav-range-dates",
      hasDrawdown
        ? `${formatChartDate(rows[troughIndex].日期)} — ${
            recoveryIndex === null
              ? "至今（修复中）"
              : formatChartDate(rows[recoveryIndex].日期)
          }`
        : "持续创新高",
    );
    svg.setAttribute(
      "aria-label",
      `${formatChartDate(rows[0].日期)}至${formatChartDate(
        rows.at(-1).日期,
      )}的区间收益曲线，最大回撤${Math.abs(maxDrawdown).toFixed(2)}%，${
        hasDrawdown
          ? recoveryIndex === null
            ? `尚未修复，已历时${elapsedRecoveryDays}天`
            : `历时${recoveryDays}天修复`
          : "区间内无回撤"
      }${
        benchmarkDrawdownAnalysis?.rows?.length
          ? `；${currentTrackBenchmark?.简称 ?? "赛道基准"}最大回撤${Math.abs(
              benchmarkDrawdownAnalysis.maxDrawdown,
            ).toFixed(2)}%，${recoveryDurationLabel(
              benchmarkDrawdownAnalysis,
            )}`
          : ""
      }`,
    );
    return;
  }
  const periodChange =
    metric === "累计收益率"
      ? lastValue - firstValue
      : ((lastValue / firstValue) - 1) * 100;
  changeElement.textContent = formatPercent(periodChange);
  changeElement.className = movementClass(periodChange);
  if (isPerformanceView) {
    const benchmarkChange = benchmarkPlotPoints.length
      ? benchmarkPlotPoints.at(-1).value
      : null;
    const relativeChange = Number.isFinite(benchmarkChange)
      ? periodChange - benchmarkChange
      : null;
    const benchmarkElement = document.querySelector("#nav-range-high");
    const relativeElement = document.querySelector("#nav-range-low");
    benchmarkElement.textContent = Number.isFinite(benchmarkChange)
      ? formatPercent(benchmarkChange)
      : "—";
    benchmarkElement.className = Number.isFinite(benchmarkChange)
      ? movementClass(benchmarkChange)
      : "";
    relativeElement.textContent = Number.isFinite(relativeChange)
      ? `${relativeChange > 0 ? "+" : ""}${relativeChange.toFixed(2)} 个百分点`
      : "—";
    relativeElement.className = Number.isFinite(relativeChange)
      ? movementClass(relativeChange)
      : "";
  } else {
    text("#nav-range-high", formatNavValue(Math.max(...values), metric));
    text("#nav-range-low", formatNavValue(Math.min(...values), metric));
  }
  text(
    "#nav-range-dates",
    `${formatChartDate(rows[0].日期)} — ${formatChartDate(rows.at(-1).日期)}`,
  );
  svg.setAttribute(
    "aria-label",
    `${formatChartDate(rows[0].日期)}至${formatChartDate(
      rows.at(-1).日期,
    )}的${config.tooltipLabel}曲线，基金涨幅${formatPercent(periodChange)}${
      benchmarkPlotPoints.length
        ? `，${currentTrackBenchmark.简称}涨幅${formatPercent(
            benchmarkPlotPoints.at(-1).value,
          )}`
        : ""
    }`,
  );
}

async function loadTrackBenchmark(key, reason = "") {
  currentTrackBenchmarkKey = key;
  const requestId = ++trackBenchmarkRequestId;
  const select = document.querySelector("#track-benchmark-select");
  const status = document.querySelector("#track-benchmark-status");
  select.value = key;
  select.disabled = true;
  status.textContent = "正在加载赛道基准…";

  try {
    let payload = trackBenchmarkCache.get(key);
    if (!payload) {
      const url =
        key === "performance_composite"
          ? `/api/benchmarks/composite?spec=${encodeURIComponent(
              performanceCompositeSpec,
            )}`
          : `/api/benchmarks/${key}`;
      const response = await fetch(url);
      payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "赛道基准加载失败");
      }
      trackBenchmarkCache.set(key, payload);
    }
    if (requestId !== trackBenchmarkRequestId) return;
    currentTrackBenchmark = payload;
    document.querySelector("#benchmark-legend-label").textContent =
      payload.简称 ?? payload.名称;
    status.textContent = reason || payload.说明 || "赛道基准已加载";
  } catch (error) {
    if (requestId !== trackBenchmarkRequestId) return;
    currentTrackBenchmark = null;
    document.querySelector("#benchmark-legend-label").textContent = "赛道基准";
    status.textContent = error.message || "赛道基准暂不可用";
  } finally {
    if (requestId === trackBenchmarkRequestId) {
      select.disabled = false;
      renderNavChart(currentNavRange, currentNavMetric);
    }
  }
}

// 把复合权重字典转成后端识别的 spec 字符串：csi_dividend:0.95,money_fund:0.05。
function buildCompositeSpec(components = {}) {
  return Object.entries(components)
    .map(([key, weight]) => `${key}:${Number(weight).toFixed(6)}`)
    .join(",");
}

// 按业绩比较基准合成的复合基准，作为一个动态选项插入下拉框顶部。
function upsertCompositeOption(recommendation) {
  const select = document.querySelector("#track-benchmark-select");
  const spec = buildCompositeSpec(recommendation.复合);
  performanceCompositeSpec = spec;
  // spec 变化时，清掉旧的复合缓存，避免沿用其他基金的复合结果。
  trackBenchmarkCache.delete("performance_composite");

  const label = (recommendation.构成 ?? [])
    .map((item) => `${item.简称} ${Math.round(item.权重 * 100)}%`)
    .join(" + ");

  let group = select.querySelector('optgroup[data-composite-group="1"]');
  if (!group) {
    group = document.createElement("optgroup");
    group.label = "业绩比较基准";
    group.dataset.compositeGroup = "1";
    select.prepend(group);
  }
  let option = group.querySelector('option[value="performance_composite"]');
  if (!option) {
    option = document.createElement("option");
    option.value = "performance_composite";
    group.append(option);
  }
  option.textContent = label ? `业绩基准（${label}）` : "业绩比较基准";
}

// 下拉框分组顺序，以及「赛道基准类型」→「下拉分组」的映射。
const BENCHMARK_GROUP_ORDER = ["股票宽基", "债券赛道", "货币现金", "股债组合"];

function benchmarkGroupOf(type) {
  if (typeof type === "string" && type.startsWith("债券")) return "债券赛道";
  if (BENCHMARK_GROUP_ORDER.includes(type)) return type;
  return "股票宽基"; // 未知类型兜底归入股票宽基。
}

// 依据 catalog 动态渲染下拉框的 optgroup/option（保留已插入的业绩比较基准复合项）。
function populateBenchmarkSelect(catalog) {
  const select = document.querySelector("#track-benchmark-select");
  const composite = select.querySelector('optgroup[data-composite-group="1"]');
  const groups = new Map();
  catalog.forEach((item) => {
    const label = benchmarkGroupOf(item.类型);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(item);
  });
  const fragment = document.createDocumentFragment();
  BENCHMARK_GROUP_ORDER.forEach((label) => {
    const items = groups.get(label);
    if (!items || !items.length) return;
    const optgroup = document.createElement("optgroup");
    optgroup.label = label;
    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.key;
      option.textContent = item.简称 || item.名称;
      optgroup.append(option);
    });
    fragment.append(optgroup);
  });
  select.replaceChildren(fragment);
  if (composite) select.prepend(composite);
}

let benchmarkSelectPopulated = null;

// 拉取 catalog 并填充下拉框，promise 缓存确保只填充一次。
function ensureBenchmarkSelectPopulated() {
  if (!benchmarkSelectPopulated) {
    benchmarkSelectPopulated = loadBenchmarkCatalog()
      .then((catalog) => {
        populateBenchmarkSelect(catalog);
        return catalog;
      })
      .catch((error) => {
        benchmarkSelectPopulated = null;
        throw error;
      });
  }
  return benchmarkSelectPopulated;
}

async function initializeTrackBenchmark(recommendation = {}) {
  currentTrackBenchmark = null;
  // 先确保下拉框已按 catalog 填充，之后设置 select.value 才能选中。
  try {
    await ensureBenchmarkSelectPopulated();
  } catch {
    // 目录加载失败时下拉框可能为空，仍按 key 尝试加载并由状态栏提示。
  }
  const select = document.querySelector("#track-benchmark-select");
  if (recommendation.key === "performance_composite" && recommendation.复合) {
    upsertCompositeOption(recommendation);
  } else {
    // 非复合基金：清掉上一只基金遗留的复合动态选项与缓存。
    select.querySelector('optgroup[data-composite-group="1"]')?.remove();
    performanceCompositeSpec = "";
    trackBenchmarkCache.delete("performance_composite");
  }
  const key = recommendation.key || "hs300";
  loadTrackBenchmark(key, recommendation.理由 || "");
}

function firstNavOnOrAfter(rows, requestedDate) {
  let low = 0;
  let high = rows.length - 1;
  let match = null;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (rows[middle].日期 >= requestedDate) {
      match = rows[middle];
      high = middle - 1;
    } else {
      low = middle + 1;
    }
  }
  return match;
}

function buildInvestmentSchedule(start, end, frequency) {
  const startDate = new Date(`${start}T00:00:00`);
  const endDate = new Date(`${end}T00:00:00`);
  if (
    Number.isNaN(startDate.getTime()) ||
    Number.isNaN(endDate.getTime()) ||
    startDate > endDate
  ) {
    return [];
  }

  const dates = [];
  if (frequency === "weekly") {
    const cursor = new Date(startDate);
    while (cursor <= endDate && dates.length < 2000) {
      dates.push(localIsoDate(cursor));
      cursor.setDate(cursor.getDate() + 7);
    }
    return dates;
  }

  const preferredDay = startDate.getDate();
  for (let index = 0; index < 1200; index += 1) {
    const scheduled = new Date(
      startDate.getFullYear(),
      startDate.getMonth() + index,
      1,
    );
    const lastDay = new Date(
      scheduled.getFullYear(),
      scheduled.getMonth() + 1,
      0,
    ).getDate();
    scheduled.setDate(Math.min(preferredDay, lastDay));
    if (scheduled > endDate) break;
    dates.push(localIsoDate(scheduled));
  }
  return dates;
}

function selectInvestmentMode(mode, recalculate = true) {
  currentInvestmentMode = mode;
  const recurring = mode === "recurring";
  document.querySelectorAll("[data-simulator-mode]").forEach((button) => {
    const active = button.dataset.simulatorMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelector("#investment-frequency-field").hidden = !recurring;
  text(
    "#investment-date-label",
    recurring ? "定投开始日期" : "买入日期",
  );
  text(
    "#investment-amount-label",
    recurring ? "每期投入金额" : "买入金额",
  );
  text(
    "#investment-count-label",
    recurring ? "定投次数" : "买入次数",
  );
  text(
    "#holding-simulator-submit",
    recurring ? "计算定投结果" : "计算持有结果",
  );
  text(
    "#simulator-description",
    recurring
      ? "从选定日期开始按周或按月投入固定金额，持续至最新净值日。"
      : "假设在选定日期一次性买入并持有至最新净值日，查看更贴近个人持有期的收益。",
  );
  if (recalculate) calculateHoldingSimulation();
}

function calculateHoldingSimulation() {
  const rows = currentNavHistory?.单位净值?.明细 ?? [];
  const dateInput = document.querySelector("#holding-start-date");
  const amountInput = document.querySelector("#holding-amount");
  const frequency = document.querySelector("#investment-frequency").value;
  const note = document.querySelector("#holding-simulator-note");
  const amount = Number(amountInput.value);
  const requestedDate = dateInput.value;

  const resetResults = (message) => {
    text("#holding-invested", "—");
    text("#investment-count", "—");
    text("#holding-return", "—");
    text("#holding-profit", "—");
    text("#holding-end-value", "—");
    text("#holding-period", "—");
    note.textContent = message;
  };

  if (rows.length < 2) {
    resetResults("该基金暂无足够的成立以来收益数据，无法进行模拟。");
    return;
  }
  if (!requestedDate || !Number.isFinite(amount) || amount < 100) {
    resetResults(
      `请选择有效开始日期，并输入不少于 100 元的${
        currentInvestmentMode === "recurring" ? "每期投入金额" : "买入金额"
      }。`,
    );
    return;
  }

  const end = rows.at(-1);
  if (requestedDate < rows[0].日期) {
    resetResults(`开始日期不能早于首个净值日期 ${rows[0].日期}。`);
    return;
  }
  if (requestedDate > end.日期) {
    resetResults(`开始日期不能晚于最新净值日期 ${end.日期}。`);
    return;
  }

  const endNav = Number(end.单位净值);
  if (!Number.isFinite(endNav) || endNav <= 0) {
    resetResults("单位净值序列存在异常，暂时无法进行模拟。");
    return;
  }

  const scheduledDates =
    currentInvestmentMode === "recurring"
      ? buildInvestmentSchedule(requestedDate, end.日期, frequency)
      : [requestedDate];
  const orders = scheduledDates
    .map((scheduledDate) => {
      const navRow = firstNavOnOrAfter(rows, scheduledDate);
      const nav = Number(navRow?.单位净值);
      if (!navRow || !Number.isFinite(nav) || nav <= 0) return null;
      return {
        scheduledDate,
        actualDate: navRow.日期,
        units: amount / nav,
      };
    })
    .filter(Boolean);
  if (!orders.length) {
    resetResults("所选区间内没有可用于投入的净值数据。");
    return;
  }

  const totalUnits = orders.reduce((sum, order) => sum + order.units, 0);
  const cashDividends = orders.reduce((cash, order) => {
    const dividendPerShare = currentDividends
      .filter(
        (dividend) =>
          dividend.除息日 > order.actualDate &&
          dividend.除息日 <= end.日期 &&
          Number.isFinite(Number(dividend.每份分红)),
      )
      .reduce((sum, dividend) => sum + Number(dividend.每份分红), 0);
    return cash + order.units * dividendPerShare;
  }, 0);
  const totalInvested = amount * orders.length;
  const endValue = totalUnits * endNav + cashDividends;
  const holdingReturn = (endValue / totalInvested - 1) * 100;
  const profit = endValue - totalInvested;
  const actualStart = orders[0].actualDate;
  const shiftedOrders = orders.filter(
    (order) => order.scheduledDate !== order.actualDate,
  ).length;
  const returnElement = document.querySelector("#holding-return");
  const profitElement = document.querySelector("#holding-profit");
  text("#holding-invested", formatCurrency(totalInvested));
  text("#investment-count", `${orders.length} 次`);
  returnElement.textContent = formatPercent(holdingReturn);
  returnElement.className = movementClass(holdingReturn);
  profitElement.textContent = formatCurrency(profit, true);
  profitElement.className = movementClass(profit);
  text("#holding-end-value", formatCurrency(endValue));
  text(
    "#holding-period",
    `${formatChartDate(actualStart)} — ${formatChartDate(end.日期)}`,
  );
  if (currentInvestmentMode === "recurring") {
    const frequencyLabel = frequency === "weekly" ? "每周" : "每月";
    note.textContent = `${frequencyLabel}投入，共 ${orders.length} 期${
      shiftedOrders ? `，其中 ${shiftedOrders} 期顺延至下一有效净值日` : ""
    }；期间现金分红约 ${formatCurrency(cashDividends)}，不计申购、赎回费用。`;
  } else {
    note.textContent =
      actualStart === requestedDate
        ? `按单位净值估算，期间现金分红约 ${formatCurrency(cashDividends)}；不计申购、赎回费用。`
        : `所选日期无净值数据，已从下一可用日期 ${formatChartDate(actualStart)} 起算；期间现金分红约 ${formatCurrency(cashDividends)}，不计交易费用。`;
  }
}

function renderHoldingSimulator() {
  const rows = currentNavHistory?.单位净值?.明细 ?? [];
  const dateInput = document.querySelector("#holding-start-date");
  selectInvestmentMode(currentInvestmentMode, false);
  if (rows.length < 2) {
    dateInput.value = "";
    dateInput.removeAttribute("min");
    dateInput.removeAttribute("max");
    calculateHoldingSimulation();
    return;
  }

  const firstDate = rows[0].日期;
  const endDate = rows.at(-1).日期;
  const defaultDate = new Date(`${endDate}T00:00:00`);
  defaultDate.setFullYear(defaultDate.getFullYear() - 1);
  const defaultValue = localIsoDate(defaultDate);
  dateInput.min = firstDate;
  dateInput.max = endDate;
  dateInput.value = defaultValue < firstDate ? firstDate : defaultValue;
  calculateHoldingSimulation();
}

function renderNavHistory(history) {
  currentNavHistory = history ?? {};
  currentDividends = history?.分红事件 ?? [];
  currentNavMetric = history?.默认指标 ?? "累计收益率";
  initializeCustomRange();
  renderNavChart(currentNavRange, currentNavMetric);
  renderHoldingSimulator();
}

function buildTreemapLayout(items, bounds = { x: 0, y: 0, width: 100, height: 100 }) {
  if (!items.length) return [];
  if (items.length === 1) {
    return [{ ...items[0], ...bounds }];
  }

  const total = items.reduce((sum, item) => sum + item.weight, 0);
  let firstTotal = 0;
  let splitIndex = 1;
  for (let index = 0; index < items.length - 1; index += 1) {
    const nextTotal = firstTotal + items[index].weight;
    if (Math.abs(total / 2 - nextTotal) <= Math.abs(total / 2 - firstTotal)) {
      firstTotal = nextTotal;
      splitIndex = index + 1;
    } else {
      break;
    }
  }

  const first = items.slice(0, splitIndex);
  const second = items.slice(splitIndex);
  const ratio = firstTotal / total;

  if (bounds.width >= bounds.height) {
    const firstWidth = bounds.width * ratio;
    return [
      ...buildTreemapLayout(first, { ...bounds, width: firstWidth }),
      ...buildTreemapLayout(second, {
        x: bounds.x + firstWidth,
        y: bounds.y,
        width: bounds.width - firstWidth,
        height: bounds.height,
      }),
    ];
  }

  const firstHeight = bounds.height * ratio;
  return [
    ...buildTreemapLayout(first, { ...bounds, height: firstHeight }),
    ...buildTreemapLayout(second, {
      x: bounds.x,
      y: bounds.y + firstHeight,
      width: bounds.width,
      height: bounds.height - firstHeight,
    }),
  ];
}

function renderTreemap(
  container,
  items,
  ariaLabel,
  weightScope = "基金净值",
  onActivate = null,
  interactionLabel = "查看股票详情",
) {
  container.replaceChildren();
  const normalized = items
    .map((item, index) => ({
      ...item,
      index,
      weight: Math.max(Number(item.weight) || 0, 0),
    }))
    .filter((item) => item.weight > 0)
    .sort((a, b) => b.weight - a.weight);

  if (!normalized.length) {
    container.hidden = true;
    return 0;
  }

  container.hidden = false;
  const total = normalized.reduce((sum, item) => sum + item.weight, 0);
  const layout = buildTreemapLayout(normalized);
  layout.forEach((item, index) => {
    const cell = document.createElement("div");
    const area = item.width * item.height;
    const colorIndex = index % palette.length;
    cell.className = "treemap-cell";
    if (area < 900) cell.classList.add("compact");
    if (area < 330) cell.classList.add("micro");
    cell.style.left = `${item.x}%`;
    cell.style.top = `${item.y}%`;
    cell.style.width = `${item.width}%`;
    cell.style.height = `${item.height}%`;
    cell.style.background = palette[colorIndex];
    cell.style.color = [1, 2, 3].includes(colorIndex)
      ? "var(--ink)"
      : "var(--paper-light)";
    cell.style.setProperty("--cell-delay", `${Math.min(index * 45, 360)}ms`);
    const itemLabel = `${item.name}${item.code ? ` · ${item.code}` : ""}：占${weightScope} ${item.weight.toFixed(2)}%`;
    const interactive = Boolean(onActivate);
    cell.tabIndex = interactive ? 0 : -1;
    cell.title = interactive ? `${itemLabel}，点击${interactionLabel}` : itemLabel;
    if (interactive) {
      const activate = () => onActivate(item);
      cell.classList.add("interactive");
      if (!item.code) cell.classList.add("guide-interactive");
      cell.setAttribute("role", "button");
      cell.setAttribute("aria-label", `${itemLabel}，${interactionLabel}`);
      cell.addEventListener("click", activate);
      cell.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        activate();
      });
    }

    const name = document.createElement("span");
    name.className = "treemap-name";
    name.textContent = item.name;
    const weight = document.createElement("strong");
    weight.textContent = `${formatNumber(item.weight, 2)}%`;
    cell.append(name, weight);
    if (item.code) {
      const code = document.createElement("small");
      code.textContent = item.code;
      if (item.hk) {
        const badge = document.createElement("span");
        badge.className = "treemap-market-badge hk";
        badge.textContent = "HK";
        badge.title = "港股";
        code.append(document.createTextNode(" "), badge);
      }
      cell.append(code);
    }
    container.append(cell);
  });

  container.setAttribute(
    "aria-label",
    `${ariaLabel}，共 ${normalized.length} 项，合计占${weightScope} ${total.toFixed(2)}%`,
  );
  container.setAttribute("role", onActivate ? "group" : "img");
  return total;
}

function renderSectorMatrix(holdingGroup, type) {
  const container = document.querySelector("#sector-treemap");
  const empty = document.querySelector("#sector-empty");
  const note = document.querySelector("#sector-note");
  const viewTabs = document.querySelector("#structure-view-tabs");
  let group = {};
  let rows = [];
  let nameKey = "行业类别";
  let chartLabel = "股票行业配置矩阵图";
  const weightScope =
    type === "穿透" ? "目标 ETF 净值" : "基金净值";

  viewTabs.replaceChildren();
  if (type === "债券") {
    const bondGroup = currentHoldings?.债券持仓 ?? {};
    const views = {
      品种: {
        group: bondGroup.品种结构 ?? {},
        nameKey: "债券品种",
        eyebrow: "BOND TYPE",
        title: "债券品种结构",
        totalLabel: "完整组合占净值",
      },
      信用属性: {
        group: {
          ...(bondGroup.品种结构?.信用属性 ?? {}),
          报告期: bondGroup.品种结构?.报告期,
        },
        nameKey: "信用属性",
        eyebrow: "CREDIT PROFILE",
        title: "利率债 / 信用债",
        totalLabel: "归并结构占净值",
      },
    };
    const availableViews = Object.entries(views).filter(
      ([, config]) => (config.group.明细 ?? []).length,
    );
    if (
      !(views[currentBondStructureView]?.group?.明细 ?? []).length &&
      availableViews.length
    ) {
      currentBondStructureView = availableViews[0][0];
    }
    const view = views[currentBondStructureView] ?? views.品种;
    group = view.group;
    rows = group.明细 ?? [];
    nameKey = view.nameKey;
    chartLabel = `${view.title}矩阵图`;
    text("#structure-map-label", view.eyebrow);
    text("#structure-map-title", view.title);
    text("#sector-total-share-label", view.totalLabel);
    viewTabs.hidden = availableViews.length < 2;
    availableViews.forEach(([viewName]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "structure-view-tab";
      button.textContent = viewName;
      const active = viewName === currentBondStructureView;
      button.classList.toggle("active", active);
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(active));
      button.addEventListener("click", () => {
        currentBondStructureView = viewName;
        renderSectorMatrix(holdingGroup, type);
      });
      viewTabs.append(button);
    });
  } else if (type === "基金") {
    const totals = new Map();
    (holdingGroup?.明细 ?? []).forEach((row) => {
      const fundType = row.基金类型 ?? row.运作方式 ?? "基金投资";
      totals.set(
        fundType,
        (totals.get(fundType) ?? 0) + (Number(row.占净值比例) || 0),
      );
    });
    group = {
      报告期: holdingGroup?.报告期,
      口径: holdingGroup?.口径,
      说明: holdingGroup?.说明,
    };
    rows = [...totals].map(([基金类型, 占净值比例]) => ({
      基金类型,
      占净值比例,
    }));
    nameKey = "基金类型";
    chartLabel = "基金投资结构矩阵图";
    viewTabs.hidden = true;
    text("#structure-map-label", "FUND EXPOSURE");
    text("#structure-map-title", "基金投资结构");
    text("#sector-total-share-label", "基金投资占净值");
  } else {
    group =
      type === "穿透"
        ? holdingGroup?.板块配置 ?? {}
        : currentHoldings?.板块配置 ?? {};
    rows = group.明细 ?? [];
    viewTabs.hidden = true;
    text("#structure-map-label", "SECTOR MAP");
    text("#structure-map-title", "行业 / 板块矩阵");
    text(
      "#sector-total-share-label",
      type === "穿透" ? "ETF行业内部占比" : "股票行业占净值",
    );
  }

  const total = renderTreemap(
    container,
    rows.map((row) => ({
      name: row[nameKey] ?? "未分类",
      weight: row.占净值比例,
    })),
    chartLabel,
    weightScope,
    type === "债券"
      ? (item) =>
          openBondStructureHelp(
            item.name,
            currentBondStructureView,
            item.weight,
          )
      : null,
    "查看类别介绍、特点和收益风险",
  );
  text("#sector-total-share", `${formatNumber(total, 1)}%`);

  empty.hidden = Boolean(rows.length);
  if (!rows.length) {
    empty.textContent =
      group.说明 ??
      (type === "债券"
        ? "最新季报暂未提供可解析的债券结构。"
        : type === "基金"
          ? "最新季报暂未提供可解析的基金投资结构。"
          : type === "穿透"
            ? "AKShare 暂未返回目标 ETF 的行业配置。"
            : "AKShare 暂无该基金的股票行业配置。");
  }
  note.textContent = rows.length
    ? `${group.报告期 ?? "最新报告期"} · ${group.口径 ?? "股票行业配置"}${
        group.说明 ? ` · ${group.说明}` : ""
      }${type === "债券" ? " · 点击矩阵查看类别说明" : ""}`
    : type === "债券"
      ? "债券结构暂不可用，不根据名称猜测品种或期限。"
      : type === "基金"
        ? "基金投资结构来自季度报告披露。"
        : type === "穿透"
          ? "目标 ETF 暂无可用行业配置。"
          : "仅展示官方披露数据，不根据证券名称推测行业。";
}

function renderAssetAllocation(allocation) {
  const bar = document.querySelector("#asset-allocation-bar");
  const stats = document.querySelector("#asset-allocation-stats");
  const details = allocation?.明细 ?? [];
  const categoryColors = {
    股票: "#d33b28",
    债券: "#14745a",
    基金: "#d7a928",
    其他: "#73776f",
  };

  bar.replaceChildren();
  stats.replaceChildren();
  text("#asset-allocation-period", allocation?.报告期, "暂无报告期");
  renderTargetFundDisclosure();

  if (!details.length) {
    bar.classList.add("empty");
    bar.setAttribute("aria-label", "暂无可用的基金资产分布");
    const empty = document.createElement("span");
    empty.className = "asset-allocation-empty";
    empty.textContent = "最新季报暂未提供可解析的资产分布";
    bar.append(empty);
    text(
      "#asset-allocation-note",
      allocation?.说明,
      "资产分布暂不可用，持仓明细仍按基金净值口径展示。",
    );
    return;
  }

  bar.classList.remove("empty");
  const ariaParts = [];
  details.forEach((item) => {
    const category = item.资产类别 ?? "其他";
    const share = Math.max(Number(item.占比) || 0, 0);
    const color = categoryColors[category] ?? categoryColors.其他;
    ariaParts.push(`${category} ${share.toFixed(2)}%`);

    if (share > 0) {
      const segment = document.createElement("div");
      segment.className = "asset-allocation-segment";
      segment.style.width = `${share}%`;
      segment.style.background = color;
      segment.title = `${category}：${share.toFixed(2)}%`;
      if (share >= 9) {
        const segmentLabel = document.createElement("span");
        segmentLabel.textContent = category;
        segment.append(segmentLabel);
      }
      bar.append(segment);
    }

    const card = document.createElement("div");
    card.className = "asset-allocation-stat";
    card.style.setProperty("--asset-color", color);
    const label = document.createElement("span");
    label.textContent = category;
    const value = document.createElement("strong");
    value.textContent = `${formatNumber(share, 2)}%`;
    card.append(label, value);
    stats.append(card);
  });
  bar.setAttribute("aria-label", `基金资产分布：${ariaParts.join("，")}`);
  text(
    "#asset-allocation-note",
    `${allocation?.说明 ?? "来自最新季度报告。"}${
      allocation?.公告日期 ? ` · 公告于 ${allocation.公告日期}` : ""
    }`,
  );
}

function renderTargetFundDisclosure() {
  const panel = document.querySelector("#target-fund-disclosure");
  const fundGroup = currentHoldings?.基金投资 ?? {};
  const rows = fundGroup.明细 ?? [];
  const targetFund =
    fundGroup.类型 === "目标ETF" && rows.length === 1 ? rows[0] : null;

  panel.hidden = !targetFund;
  if (!targetFund) return;

  text("#target-fund-name", targetFund.基金名称, "目标 ETF");
  text("#target-fund-code", targetFund.基金代码, "代码未知");
  text(
    "#target-fund-weight",
    targetFund.占净值比例 == null
      ? "—"
      : `${formatNumber(targetFund.占净值比例, 2)}%`,
  );
  text(
    "#target-fund-market-value",
    targetFund.持仓市值 == null
      ? "—"
      : `${formatNumber(targetFund.持仓市值, 2)} 万元`,
  );
  const penetrated = Boolean(currentHoldings?.ETF穿透?.可用);
  const status = document.querySelector("#target-fund-status");
  status.classList.toggle("pending", !penetrated);
  status.querySelector("span").textContent = penetrated
    ? "下方股票持仓已穿透自该基金"
    : "目标 ETF 原始持仓";
}

function renderStockFundamentals(group, type) {
  const panel = document.querySelector("#stock-fundamentals-panel");
  const summary = group?.估值概览 ?? {};
  const visible = type !== "债券" && Boolean(summary.可用);
  panel.hidden = !visible;
  if (!visible) return;

  const aggregate = summary.组合指标 ?? {};
  const coverage = summary.指标覆盖 ?? {};
  text(
    "#stock-fundamentals-coverage",
    `${summary.覆盖数量 ?? 0} / ${summary.持仓数量 ?? 0}`,
  );
  text(
    "#stock-weighted-pe",
    aggregate.PE == null ? "—" : `${formatNumber(aggregate.PE, 2)}×`,
  );
  text(
    "#stock-weighted-pb",
    aggregate.PB == null ? "—" : `${formatNumber(aggregate.PB, 2)}×`,
  );
  text(
    "#stock-weighted-roe",
    aggregate.ROE == null ? "—" : `${formatNumber(aggregate.ROE, 2)}%`,
  );
  text(
    "#stock-weighted-dividend-yield",
    aggregate.股息率 == null
      ? "—"
      : `${formatNumber(aggregate.股息率, 2)}%`,
  );
  text(
    "#stock-fundamentals-note",
    `${summary.说明 ?? summary.口径 ?? ""}${
      summary.估值日期 ? ` · 行情日期 ${summary.估值日期}` : ""
    }`,
  );

  [
    ["#stock-weighted-pe", "PE"],
    ["#stock-weighted-pb", "PB"],
    ["#stock-weighted-roe", "ROE"],
    ["#stock-weighted-dividend-yield", "股息率"],
  ].forEach(([selector, key]) => {
    const detail = coverage[key] ?? {};
    document.querySelector(selector).title =
      `覆盖 ${detail.数量 ?? 0} 只股票，合计占净值 ${formatNumber(
        detail.占净值比例,
        2,
      )}%`;
  });
}

function stockMetricText(value, unit) {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    !Number.isFinite(Number(value))
  ) {
    return "—";
  }
  return `${formatNumber(value, 2)}${unit}`;
}

function stockRowsForRange(range) {
  const rows = currentStockDetail?.价格趋势?.明细 ?? [];
  return filterNavRows(rows, range);
}

function renderStockPriceChart(range = currentStockRange) {
  currentStockRange = range;
  document.querySelectorAll("[data-stock-range]").forEach((button) => {
    const active = button.dataset.stockRange === range;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });

  const svg = document.querySelector("#stock-price-chart");
  const empty = document.querySelector("#stock-chart-empty");
  const tooltip = document.querySelector("#stock-chart-tooltip");
  const rows = stockRowsForRange(range)
    .map((row) => ({ ...row, 收盘: Number(row.收盘) }))
    .filter((row) => row.日期 && Number.isFinite(row.收盘));
  svg.replaceChildren();
  stockPlotPoints = [];
  tooltip.hidden = true;
  empty.hidden = rows.length >= 2;

  if (rows.length < 2) {
    text("#stock-range-change", null);
    text("#stock-range-high", null);
    text("#stock-range-low", null);
    text("#stock-range-dates", null);
    return;
  }

  const width = 1000;
  const height = 340;
  const margin = { top: 24, right: 24, bottom: 42, left: 72 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const startTime = new Date(`${rows[0].日期}T00:00:00`).getTime();
  const endTime = new Date(`${rows.at(-1).日期}T00:00:00`).getTime();
  const closes = rows.map((row) => row.收盘);
  const rawMin = Math.min(...closes);
  const rawMax = Math.max(...closes);
  const padding = Math.max((rawMax - rawMin) * 0.08, rawMax * 0.015, 0.01);
  const minValue = Math.max(0, rawMin - padding);
  const maxValue = rawMax + padding;
  const xFor = (isoDate) => {
    const time = new Date(`${isoDate}T00:00:00`).getTime();
    return margin.left +
      ((time - startTime) / Math.max(endTime - startTime, 1)) * plotWidth;
  };
  const yFor = (value) =>
    margin.top +
    ((maxValue - Number(value)) / Math.max(maxValue - minValue, 0.0001)) *
      plotHeight;

  const defs = svgNode("defs");
  const gradient = svgNode("linearGradient", {
    id: "stock-price-gradient",
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1",
  });
  gradient.append(
    svgNode("stop", {
      offset: "0%",
      "stop-color": "#d33b28",
      "stop-opacity": "0.23",
    }),
    svgNode("stop", {
      offset: "100%",
      "stop-color": "#d33b28",
      "stop-opacity": "0",
    }),
  );
  defs.append(gradient);
  svg.append(defs);

  const grid = svgNode("g", { class: "stock-price-grid" });
  buildYAxisTicks(minValue, maxValue).forEach((value) => {
    const y = yFor(value);
    grid.append(
      svgNode("line", {
        x1: margin.left,
        y1: y,
        x2: width - margin.right,
        y2: y,
      }),
    );
    const label = svgNode("text", {
      x: margin.left - 12,
      y: y + 4,
      "text-anchor": "end",
    });
    label.textContent = formatNumber(value, 2);
    grid.append(label);
  });
  for (let index = 0; index < 5; index += 1) {
    const ratio = index / 4;
    const time = startTime + ratio * (endTime - startTime);
    const x = margin.left + ratio * plotWidth;
    grid.append(
      svgNode("line", {
        x1: x,
        y1: margin.top,
        x2: x,
        y2: height - margin.bottom,
      }),
    );
    const label = svgNode("text", {
      x,
      y: height - 16,
      "text-anchor": index === 0 ? "start" : index === 4 ? "end" : "middle",
    });
    label.textContent = formatChartDate(
      localIsoDate(new Date(time)),
      range !== "1m",
    );
    grid.append(label);
  }
  svg.append(grid);

  stockPlotPoints = rows.map((row) => ({
    ...row,
    value: row.收盘,
    x: xFor(row.日期),
    y: yFor(row.收盘),
  }));
  const linePath = stockPlotPoints
    .map(
      (point, index) =>
        `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`,
    )
    .join(" ");
  const baseline = height - margin.bottom;
  const areaPath = `${linePath} L${stockPlotPoints
    .at(-1)
    .x.toFixed(2)},${baseline} L${stockPlotPoints[0].x.toFixed(
    2,
  )},${baseline} Z`;
  svg.append(
    svgNode("path", { d: areaPath, class: "stock-price-area" }),
    svgNode("path", { d: linePath, class: "stock-price-line" }),
  );

  const crosshair = svgNode("g", {
    id: "stock-price-crosshair",
    class: "stock-price-crosshair",
    visibility: "hidden",
  });
  crosshair.append(
    svgNode("line", {
      x1: 0,
      y1: margin.top,
      x2: 0,
      y2: baseline,
    }),
    svgNode("circle", { cx: 0, cy: 0, r: 5 }),
  );
  svg.append(crosshair);

  const first = rows[0].收盘;
  const last = rows.at(-1).收盘;
  const change = first > 0 ? (last / first - 1) * 100 : null;
  const changeElement = document.querySelector("#stock-range-change");
  changeElement.textContent = Number.isFinite(change)
    ? formatPercent(change)
    : "—";
  changeElement.className = Number.isFinite(change)
    ? movementClass(change)
    : "";
  const priceUnit = stockCurrencyUnit(
    currentStockDetail?.基础信息?.货币,
    currentStockDetail?.基础信息?.市场类型,
  );
  text("#stock-range-high", `${formatNumber(rawMax, 2)} ${priceUnit}`);
  text("#stock-range-low", `${formatNumber(rawMin, 2)} ${priceUnit}`);
  text(
    "#stock-range-dates",
    `${formatChartDate(rows[0].日期)} — ${formatChartDate(rows.at(-1).日期)}`,
  );
  svg.setAttribute(
    "aria-label",
    `${formatChartDate(rows[0].日期)}至${formatChartDate(
      rows.at(-1).日期,
    )}的前复权收盘价曲线，区间涨跌${formatPercent(change)}`,
  );
}

function dailyCacheLabel(cache) {
  const statusLabels = {
    HIT: "日缓存命中",
    MISS: cache?.强制刷新 ? "已强制刷新" : "已更新日缓存",
    STALE: "上游暂不可用 · 使用旧缓存",
  };
  const label = statusLabels[cache?.状态] ?? "日缓存";
  if (!cache?.下次更新) return `${label} · 收盘后更新`;
  const refreshAt = new Date(cache.下次更新);
  if (Number.isNaN(refreshAt.getTime())) return `${label} · 收盘后更新`;
  return `${label} · 下次检查 ${refreshAt.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })}`;
}

function renderStockDetail(data, range = "1y") {
  currentStockDetail = data;
  const basic = data.基础信息 ?? {};
  const quote = data.行情 ?? {};
  const metrics = data.指标 ?? {};
  text("#stock-detail-name", basic.名称, "未知股票");
  text("#stock-detail-code", basic.代码);
  const stockXueqiuLink = document.querySelector("#stock-xueqiu-link");
  const stockXueqiuHref = stockXueqiuUrl(basic.代码, basic.市场);
  stockXueqiuLink.hidden = !stockXueqiuHref;
  stockXueqiuLink.href = stockXueqiuHref || "#";
  stockXueqiuLink.title = stockXueqiuHref
    ? `在雪球查看${basic.名称 ?? "该股票"}`
    : "";
  const isHk = basic.市场类型 === "HK" || isHkStockCode(basic.代码);
  const codeElement = document.querySelector("#stock-detail-code");
  if (codeElement) {
    let badge = codeElement.parentElement.querySelector(".stock-market-badge");
    if (isHk) {
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "stock-market-badge hk";
        codeElement.insertAdjacentElement("afterend", badge);
      }
      badge.textContent = "HK 港股";
      badge.hidden = false;
    } else if (badge) {
      badge.hidden = true;
    }
  }
  const priceUnit = stockCurrencyUnit(basic.货币, basic.市场类型);
  text("#stock-detail-industry", basic.行业, "行业暂无");
  text("#stock-detail-market", basic.市场, "市场暂无");
  text(
    "#stock-detail-listed",
    basic.上市日期 ? `上市于 ${basic.上市日期}` : "上市日期暂无",
  );
  text(
    "#stock-detail-price",
    quote.最新价 == null ? null : `${formatNumber(quote.最新价, 2)} ${priceUnit}`,
  );
  const changeElement = document.querySelector("#stock-detail-change");
  changeElement.textContent =
    quote.涨跌幅 == null ? "涨跌幅暂无" : formatPercent(quote.涨跌幅);
  changeElement.className =
    quote.涨跌幅 == null ? "" : movementClass(quote.涨跌幅);
  text(
    "#stock-detail-price-date",
    quote.行情日期 ? `行情日期 ${quote.行情日期}` : "行情日期暂无",
  );
  text("#stock-detail-pe", stockMetricText(metrics.PE, "×"));
  text("#stock-detail-pb", stockMetricText(metrics.PB, "×"));
  text("#stock-detail-roe", stockMetricText(metrics.ROE, "%"));
  text(
    "#stock-detail-dividend-yield",
    stockMetricText(metrics.股息率, "%"),
  );
  text(
    "#stock-detail-turnover",
    stockMetricText(metrics.换手率, "%"),
  );
  text("#stock-detail-metric-note", metrics.说明, "查询时点数据");
  text("#stock-detail-cache-note", dailyCacheLabel(data._缓存));
  const refreshButton = document.querySelector("#stock-detail-refresh");
  refreshButton.disabled = false;
  refreshButton.querySelector("span").textContent = "强制刷新";

  const warnings = data.提示 ?? [];
  const warningElement = document.querySelector("#stock-detail-warnings");
  warningElement.hidden = !warnings.length;
  warningElement.textContent = warnings.join("；");
  text(
    "#stock-detail-query-time",
    data.查询时间
      ? `查询于 ${new Date(data.查询时间).toLocaleString("zh-CN", {
          hour12: false,
        })}`
      : null,
  );
  currentStockRange = range;
  renderStockPriceChart(range);
}

async function openStockDetail(code, fallback = {}, forceRefresh = false) {
  const normalized = normalizeStockCode(code);
  if (!validateStockCode(normalized)) return;
  const dialog = document.querySelector("#stock-detail-dialog");
  const loading = document.querySelector("#stock-detail-loading");
  const error = document.querySelector("#stock-detail-error");
  const content = document.querySelector("#stock-detail-content");
  const refreshButton = document.querySelector("#stock-detail-refresh");
  const requestId = ++stockDetailRequestId;
  const requestedRange = forceRefresh ? currentStockRange : "1y";
  currentStockCode = normalized;
  currentStockFallback = fallback;
  currentStockDetail = null;
  stockPlotPoints = [];
  refreshButton.disabled = true;
  refreshButton.querySelector("span").textContent = "刷新中…";
  loading.hidden = false;
  error.hidden = true;
  content.hidden = true;
  if (!dialog.open) dialog.showModal();

  try {
    const params = new URLSearchParams();
    if (forceRefresh) params.set("refresh", "true");
    const queryString = params.toString();
    const query = queryString ? `?${queryString}` : "";
    const response = await fetch(`/api/stocks/${normalized}${query}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(
        payload.detail || `股票查询失败（HTTP ${response.status}）`,
      );
    }
    if (requestId !== stockDetailRequestId) return;
    payload.基础信息 ??= {};
    payload.基础信息.名称 ??= fallback.名称;
    payload.基础信息.行业 ??= fallback.行业;
    payload._缓存 = {
      状态: response.headers.get("X-Cache"),
      新鲜度: response.headers.get("X-Cache-Status"),
      数据日期: response.headers.get("X-Data-Date"),
      下次更新: response.headers.get("X-Next-Refresh"),
      强制刷新: forceRefresh,
    };
    renderStockDetail(payload, requestedRange);
    loading.hidden = true;
    content.hidden = false;
    document.querySelector(".stock-detail-sheet").scrollTop = 0;
  } catch (requestError) {
    if (requestId !== stockDetailRequestId) return;
    loading.hidden = true;
    error.hidden = false;
    refreshButton.disabled = false;
    refreshButton.querySelector("span").textContent = "强制刷新";
    text(
      "#stock-detail-error-message",
      requestError.message,
      "请稍后重试。",
    );
  }
}

function renderHoldingGroup(group, type) {
  const rows = group?.明细 ?? [];
  const tableBody = document.querySelector("#holdings-table");
  const noHoldings = document.querySelector("#no-holdings");
  const holdingTreemap = document.querySelector("#holding-treemap");
  const quantityHeading = document.querySelector("#quantity-heading");
  const weightHeading = document.querySelector("#holding-weight-heading");
  const isBond = type === "债券";
  const isFund = type === "基金";
  const isPenetration = type === "穿透";
  const isStock = !isBond && !isFund;
  const targetEtfPenetration = usesTargetEtfPenetrationView();
  const penetration = currentHoldings?.ETF穿透 ?? {};
  const target = penetration.目标ETF ?? {};
  const context = document.querySelector("#holdings-context");
  const holdingsTable = tableBody.closest("table");
  const stockOnlyHeadings = document.querySelectorAll(
    ".stock-industry-column, .stock-fundamental-column",
  );

  text("#holdings-period", group?.报告期, "暂无报告期");
  text("#holdings-count", rows.length, "0");
  text(
    "#security-map-title",
    isPenetration
      ? targetEtfPenetration
        ? "股票持仓矩阵"
        : "目标 ETF 穿透矩阵"
      : isFund
        ? "基金投资矩阵"
        : penetration.可用 && type === "股票"
          ? "直接股票持仓矩阵"
          : `${type}持仓矩阵`,
  );
  text(
    "#top-holdings-share-label",
    isPenetration ? "ETF内部列示占比" : "已列示占净值",
  );
  text(
    "#security-map-note",
    isPenetration
      ? "矩形面积为目标 ETF 内部权重，尚未乘以联接基金持有目标 ETF 的比例。"
      : isFund
        ? "矩形面积按季度报告披露的基金投资占基金净值比例分配。"
        : isBond
          ? "矩形面积按最新报告披露的各只债券占基金净值比例分配。"
          : penetration.可用 && type === "股票"
            ? "矩形面积按各项占联接基金净值比例分配，标签显示实际比例。"
            : "矩形面积按各项占基金净值比例分配，标签显示实际比例。",
  );
  if (isPenetration) {
    context.hidden = false;
    context.textContent = `穿透目标：${target.名称 ?? "目标 ETF"} · ${target.代码 ?? "代码未知"}`;
  } else if (isFund) {
    context.hidden = false;
    context.textContent =
      group?.说明 ?? "以下为季度报告披露的基金或 ETF 投资。";
  } else if (penetration.可用 && type === "股票") {
    context.hidden = false;
    context.textContent = "以下为联接基金直接持有的股票，不包含目标 ETF 内部持仓。";
  } else {
    context.hidden = true;
    context.textContent = "";
  }
  tableBody.replaceChildren();
  quantityHeading.hidden = isBond || isFund;
  stockOnlyHeadings.forEach((heading) => {
    heading.hidden = !isStock;
  });
  holdingsTable.classList.toggle("stock-fundamentals-visible", isStock);
  weightHeading.textContent = isPenetration ? "ETF内部占比" : "占净值";
  renderStockFundamentals(group, type);
  renderSectorMatrix(group, type);

  if (!rows.length) {
    noHoldings.hidden = false;
    holdingTreemap.replaceChildren();
    holdingTreemap.hidden = true;
    text("#top-holdings-share", "0%");
    return;
  }

  noHoldings.hidden = true;
  const maxWeight = Math.max(
    ...rows.map((row) => Number(row.占净值比例) || 0),
    1,
  );

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const rank = document.createElement("td");
    rank.className = "holding-rank";
    rank.textContent = String(row.持仓排名 ?? "—").padStart(2, "0");

    const security = document.createElement("td");
    const bondLink = isBond ? bondOfficialLink(row) : "";
    const name = document.createElement(
      isStock ? "button" : bondLink ? "a" : "span",
    );
    name.className = isStock
      ? "stock-detail-trigger"
      : bondLink
        ? "security-name bond-external-link"
        : "security-name";
    if (isStock) {
      name.type = "button";
      name.title = "查看股票基础资料、估值指标和收盘价趋势";
      name.addEventListener("click", () =>
        openStockDetail(row.股票代码, {
          名称: row.股票名称,
          行业: row.所属行业,
        }),
      );
    } else if (bondLink) {
      name.href = bondLink;
      name.target = "_blank";
      name.rel = "noopener noreferrer";
      name.title = "使用 Google 搜索债券名称和代码";
    }
    name.textContent = isBond
      ? row.债券名称 ?? "未知债券"
      : isFund
        ? row.基金名称 ?? "未知基金"
        : row.股票名称 ?? "未知股票";
    const code = document.createElement("span");
    code.className = "security-code";
    code.textContent = isBond
      ? [
          row.债券代码,
          row.债券类型,
          row.到期日 ? `到期 ${row.到期日}` : null,
        ]
          .filter(Boolean)
          .join(" · ") || "—"
      : isFund
        ? [row.基金代码, row.基金类型, row.运作方式]
            .filter(Boolean)
            .join(" · ") || "—"
        : row.股票代码 ?? "—";
    security.append(name, code);
    if (isStock && (row.市场 === "HK" || isHkStockCode(row.股票代码))) {
      const badge = document.createElement("span");
      badge.className = "stock-market-badge hk";
      badge.textContent = "HK";
      badge.title = "港股";
      code.append(document.createTextNode(" "), badge);
    }

    const industry = document.createElement("td");
    industry.className = "stock-industry-cell";
    industry.hidden = !isStock;
    industry.textContent = row.所属行业 ?? "—";

    const weight = document.createElement("td");
    weight.className = "weight-cell";
    const weightValue = document.createElement("span");
    weightValue.className = "weight-value";
    weightValue.textContent = `${formatNumber(row.占净值比例, 2)}%`;
    const track = document.createElement("span");
    track.className = "weight-track";
    const fill = document.createElement("i");
    fill.style.width = `${Math.min(((Number(row.占净值比例) || 0) / maxWeight) * 100, 100)}%`;
    track.append(fill);
    weight.append(weightValue, track);

    const shares = document.createElement("td");
    shares.hidden = isBond || isFund;
    shares.textContent = `${formatNumber(row.持股数, 2)} 万股`;

    const stockMetrics = [
      ["PE", "×"],
      ["PB", "×"],
      ["ROE", "%"],
      ["股息率", "%"],
    ].map(([key, unit]) => {
      const cell = document.createElement("td");
      cell.className = "stock-fundamental-cell";
      cell.hidden = !isStock;
      cell.textContent =
        row[key] == null ? "—" : `${formatNumber(row[key], 2)}${unit}`;
      return cell;
    });

    const marketValue = document.createElement("td");
    marketValue.textContent = `${formatNumber(row.持仓市值, 2)} 万元`;

    tr.append(
      rank,
      security,
      industry,
      weight,
      ...stockMetrics,
      shares,
      marketValue,
    );
    tableBody.append(tr);
  });

  const total = renderTreemap(
    holdingTreemap,
    rows.map((row) => ({
      name: isBond
        ? row.债券名称 ?? "未知债券"
        : isFund
          ? row.基金名称 ?? "未知基金"
          : row.股票名称 ?? "未知股票",
      code: isBond
        ? row.债券代码
        : isFund
          ? row.基金代码
          : row.股票代码,
      industry: isStock ? row.所属行业 : null,
      hk: isStock && (row.市场 === "HK" || isHkStockCode(row.股票代码)),
      weight: row.占净值比例,
    })),
    isPenetration ? "目标 ETF 穿透持仓矩阵图" : `${type}持仓矩阵图`,
    isPenetration ? "目标 ETF 净值" : "基金净值",
    isStock
      ? (item) =>
          openStockDetail(item.code, {
            名称: item.name,
            行业: item.industry,
          })
      : null,
  );
  text("#top-holdings-share", `${formatNumber(total, 1)}%`);
}

function holdingGroupConfig(type) {
  const penetrationAvailable = Boolean(currentHoldings?.ETF穿透?.可用);
  const targetEtfPenetration = usesTargetEtfPenetrationView();
  const configs = {
    穿透: {
      key: "ETF穿透",
      label: targetEtfPenetration ? "股票持仓" : "ETF穿透",
    },
    基金: {
      key: "基金投资",
      label: "基金持仓",
    },
    股票: {
      key: "股票持仓",
      label: penetrationAvailable ? "直接股票" : "股票持仓",
    },
    债券: {
      key: "债券持仓",
      label: "债券持仓",
    },
  };
  return configs[type];
}

function usesTargetEtfPenetrationView() {
  const fundGroup = currentHoldings?.基金投资 ?? {};
  return (
    fundGroup.类型 === "目标ETF" &&
    (fundGroup.明细 ?? []).length === 1 &&
    Boolean(currentHoldings?.ETF穿透?.可用)
  );
}

function quarterKeyFromPeriod(period) {
  const matched = String(period ?? "").match(/(20\d{2})年(?:第)?([1-4])季度/);
  return matched ? `${matched[1]}Q${matched[2]}` : "";
}

function quarterLabel(periodKey) {
  const matched = String(periodKey ?? "").match(/^(20\d{2})Q([1-4])$/);
  return matched ? `${matched[1]}年第${matched[2]}季度` : periodKey;
}

function setHoldingsQuarterStatus(message, state = "ready") {
  const status = document.querySelector("#holdings-quarter-status");
  status.dataset.state = state;
  status.querySelector("span").textContent = message;
}

function renderQuarterReportList(reports, selectedKey) {
  const list = document.querySelector("#quarter-report-list");
  list.replaceChildren();
  text("#quarter-report-count", reports.length, "0");

  if (!reports.length) {
    const empty = document.createElement("p");
    empty.className = "quarter-report-empty";
    empty.textContent = "暂无可用的季度报告目录。";
    list.append(empty);
    return;
  }

  reports.forEach((report, index) => {
    const link = document.createElement("a");
    link.className = "quarter-report-link";
    link.href = report.链接;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.classList.toggle("active", report.key === selectedKey);
    link.style.setProperty("--report-index", index);
    link.setAttribute(
      "aria-label",
      `打开${report.报告期 ?? report.key}原始季度报告`,
    );

    const sequence = document.createElement("span");
    sequence.className = "quarter-report-sequence";
    sequence.textContent = String(reports.length - index).padStart(2, "0");
    const copy = document.createElement("span");
    copy.className = "quarter-report-copy";
    const period = document.createElement("strong");
    period.textContent = report.报告期 ?? quarterLabel(report.key);
    const date = document.createElement("small");
    date.textContent = report.公告日期
      ? `公告于 ${report.公告日期}`
      : "公告日期暂无";
    copy.append(period, date);
    const action = document.createElement("span");
    action.className = "quarter-report-action";
    action.textContent = report.key === selectedKey ? "当前持仓 ↗" : "查看原文 ↗";
    link.append(sequence, copy, action);
    list.append(link);
  });
}

function initializeHoldingsExplorer(holdings) {
  const explorer = document.querySelector("#holdings-explorer");
  const select = document.querySelector("#holdings-quarter-select");
  select.disabled = false;
  document.querySelector("#holdings-content").classList.remove("is-loading");
  document.querySelector("#holdings-content").removeAttribute("aria-busy");
  currentQuarterReports = holdings?.季报列表 ?? [];
  currentHoldingsPeriodKey =
    holdings?.季度Key ?? quarterKeyFromPeriod(holdings?.报告期);

  select.replaceChildren();
  currentQuarterReports.forEach((report, index) => {
    const option = document.createElement("option");
    option.value = report.key;
    option.textContent = `${report.报告期 ?? quarterLabel(report.key)}${
      index === 0 ? " · 最新披露" : ""
    }`;
    select.append(option);
  });
  if (
    currentHoldingsPeriodKey &&
    !currentQuarterReports.some(
      (report) => report.key === currentHoldingsPeriodKey,
    )
  ) {
    const option = document.createElement("option");
    option.value = currentHoldingsPeriodKey;
    option.textContent = quarterLabel(currentHoldingsPeriodKey);
    select.prepend(option);
  }
  if (currentHoldingsPeriodKey) {
    select.value = currentHoldingsPeriodKey;
  }
  explorer.hidden = !select.options.length && !currentQuarterReports.length;
  renderQuarterReportList(
    currentQuarterReports,
    currentHoldingsPeriodKey,
  );
  setHoldingsQuarterStatus(
    currentHoldingsPeriodKey
      ? `${quarterLabel(currentHoldingsPeriodKey)} · 已展示`
      : "最新披露",
  );
  renderHoldings(holdings, false);
  // 首屏持仓为裸数据（无估值），随即补拉当前季度带估值持仓覆盖卡片。
  void enrichHoldingsForCurrentPeriod();
}

async function enrichHoldingsForCurrentPeriod() {
  const periodKey = currentHoldingsPeriodKey;
  if (!currentCode || !periodKey) return;
  // 沿用当前 holdingsRequestId：一旦用户切换季度或重新查询，本次补拉结果作废。
  const requestId = holdingsRequestId;
  try {
    const params = new URLSearchParams({
      period: periodKey,
      holdings_limit: "20",
    });
    const response = await fetch(
      `/api/funds/${currentCode}/holdings?${params}`,
    );
    if (!response.ok) return;
    const payload = await response.json();
    if (requestId !== holdingsRequestId) return;
    if (currentHoldingsPeriodKey !== periodKey) return;
    if ((payload.季报列表 ?? []).length) {
      currentQuarterReports = payload.季报列表;
    }
    renderHoldings(payload, true);
  } catch (error) {
    // 补拉失败时静默保留首屏裸持仓，不干扰已展示的基金全貌。
  }
}

async function queryHoldingsPeriod(periodKey) {
  if (!currentCode || !periodKey || periodKey === currentHoldingsPeriodKey) {
    return;
  }
  const requestId = ++holdingsRequestId;
  const previousKey = currentHoldingsPeriodKey;
  const select = document.querySelector("#holdings-quarter-select");
  const content = document.querySelector("#holdings-content");
  select.disabled = true;
  content.classList.add("is-loading");
  content.setAttribute("aria-busy", "true");
  setHoldingsQuarterStatus(
    `正在查询 ${quarterLabel(periodKey)}…`,
    "loading",
  );

  try {
    const params = new URLSearchParams({
      period: periodKey,
      holdings_limit: "20",
    });
    const response = await fetch(
      `/api/funds/${currentCode}/holdings?${params}`,
    );
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `查询失败（HTTP ${response.status}）`);
    }
    if (requestId !== holdingsRequestId) return;

    currentHoldingsPeriodKey =
      payload.季度Key ?? periodKey;
    if ((payload.季报列表 ?? []).length) {
      currentQuarterReports = payload.季报列表;
    }
    renderHoldings(payload, true);
    select.value = currentHoldingsPeriodKey;
    renderQuarterReportList(
      currentQuarterReports,
      currentHoldingsPeriodKey,
    );
    const cacheLabel =
      response.headers.get("X-Cache") === "HIT" ? "缓存命中" : "查询完成";
    setHoldingsQuarterStatus(
      `${quarterLabel(currentHoldingsPeriodKey)} · ${cacheLabel}`,
    );
  } catch (error) {
    if (requestId !== holdingsRequestId) return;
    select.value = previousKey;
    setHoldingsQuarterStatus(
      error.message || "季度持仓查询失败",
      "error",
    );
  } finally {
    if (requestId === holdingsRequestId) {
      select.disabled = false;
      content.classList.remove("is-loading");
      content.removeAttribute("aria-busy");
    }
  }
}

function selectHoldingType(type) {
  currentHoldingType = type;
  if (type === "债券") {
    currentBondStructureView = "品种";
  }
  document.querySelectorAll(".holding-tab").forEach((button) => {
    const active = button.dataset.holdingType === type;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  const config = holdingGroupConfig(type);
  renderHoldingGroup(currentHoldings?.[config.key], type);
}

function renderHoldings(holdings, preserveType = false) {
  const previousType = currentHoldingType;
  currentHoldings = holdings ?? {};
  renderAssetAllocation(currentHoldings.资产分布);
  const tabs = document.querySelector("#holdings-tabs");
  const targetEtfPenetration = usesTargetEtfPenetrationView();
  const groupOrder = targetEtfPenetration
    ? ["穿透", "股票", "债券"]
    : ["基金", "穿透", "股票", "债券"];
  const groups = groupOrder.filter(
    (type) => {
      const config = holdingGroupConfig(type);
      return (currentHoldings?.[config.key]?.明细 ?? []).length;
    },
  );

  tabs.replaceChildren();
  tabs.hidden = groups.length < 2;

  groups.forEach((type) => {
    const config = holdingGroupConfig(type);
    const button = document.createElement("button");
    const count = currentHoldings[config.key]?.明细?.length ?? 0;
    button.type = "button";
    button.className = "holding-tab";
    button.dataset.holdingType = type;
    button.setAttribute("role", "tab");
    button.textContent = `${config.label} ${count}`;
    button.addEventListener("click", () => selectHoldingType(type));
    tabs.append(button);
  });

  currentHoldingType =
    preserveType && groups.includes(previousType)
      ? previousType
      : groups[0] ?? "股票";

  if (!groups.length) {
    renderHoldingGroup(
      {
        报告期: currentHoldings?.报告期,
        明细: currentHoldings?.明细 ?? [],
      },
      currentHoldingType,
    );
    return;
  }
  selectHoldingType(currentHoldingType);
}

function renderWarnings(warnings) {
  const panel = document.querySelector("#warnings-panel");
  const list = document.querySelector("#warnings-list");
  list.replaceChildren();
  panel.hidden = !warnings?.length;
  (warnings ?? []).forEach((warning) => {
    const item = document.createElement("li");
    item.textContent = warning;
    list.append(item);
  });
}

function renderFundProfile(basic) {
  const scale = basic.基金规模 ?? {};
  const holders = basic.持有人结构 ?? {};
  const purchaseFee = basic.买入费率 ?? {};
  const feeRows = purchaseFee.明细 ?? [];
  const redeemFee = basic.赎回费率 ?? {};
  const redeemRows = redeemFee.明细 ?? [];

  text("#founded-date", basic.成立日期 ?? basic.成立日);
  text("#fund-age", basic.成立时间);
  text("#fund-scale", scale.最新净资产);
  text("#profile-summary-age", basic.成立时间);
  const managerNames = (basic.基金经理?.现任 ?? [])
    .map((manager) => manager.姓名)
    .filter(Boolean);
  text(
    "#profile-summary-manager",
    managerNames.length ? managerNames.join(" · ") : basic.管理人,
  );
  const managementRate = Number(
    String(basic.管理费率 ?? "").match(/[\d.]+/)?.[0],
  );
  const custodyRate = Number(
    String(basic.托管费率 ?? "").match(/[\d.]+/)?.[0],
  );
  const salesServiceRate = Number(
    String(basic.销售服务费率 ?? "").match(/[\d.]+/)?.[0],
  );
  const hasManagementRate = Number.isFinite(managementRate);
  const hasCustodyRate = Number.isFinite(custodyRate);
  const hasSalesServiceRate = Number.isFinite(salesServiceRate);
  const totalOperatingRate =
    (hasManagementRate ? managementRate : 0) +
    (hasCustodyRate ? custodyRate : 0) +
    (hasSalesServiceRate ? salesServiceRate : 0);
  text(
    "#profile-summary-cost",
    hasManagementRate || hasCustodyRate || hasSalesServiceRate
      ? `约 ${formatNumber(totalOperatingRate, 3)}% / 年`
      : null,
  );
  document.querySelector("#profile-summary-cost").title =
    `管理费 ${basic.管理费率 ?? "—"} + 托管费 ${basic.托管费率 ?? "—"} + 销售服务费 ${
      hasSalesServiceRate ? `${formatNumber(salesServiceRate, 3)}%（每年）` : "—"
    }`;
  text(
    "#fund-scale-date",
    scale.净资产截止日 ? `截至 ${scale.净资产截止日}` : null,
    "报告期暂无",
  );
  text("#fund-shares", scale.最新份额);
  text("#founded-scale", scale.成立份额);

  const institution = Number(holders.机构持有比例);
  const individual = Number(holders.个人持有比例);
  const hasHolderData =
    Number.isFinite(institution) && Number.isFinite(individual);
  text(
    "#holder-period",
    holders.报告期 ? `报告期 ${holders.报告期}` : null,
    "报告期暂无",
  );
  text(
    "#institution-share",
    hasHolderData ? `${formatNumber(institution, 2)}%` : null,
  );
  text(
    "#individual-share",
    hasHolderData ? `${formatNumber(individual, 2)}%` : null,
  );
  document.querySelector("#institution-bar").style.width = hasHolderData
    ? `${Math.max(institution, 0)}%`
    : "0";
  document.querySelector("#individual-bar").style.width = hasHolderData
    ? `${Math.max(individual, 0)}%`
    : "0";
  document.querySelector("#holder-bar").classList.toggle(
    "empty",
    !hasHolderData,
  );
  document
    .querySelector("#holder-bar")
    .setAttribute(
      "aria-label",
      hasHolderData
        ? `机构持有 ${institution.toFixed(2)}%，个人持有 ${individual.toFixed(2)}%`
        : "暂无基金持有人结构",
    );
  text(
    "#holder-note",
    hasHolderData
      ? `报告总份额 ${formatNumber(holders.总份额, 2)}${
          holders.总份额单位 ?? "亿份"
        } · 内部持有 ${formatNumber(holders.内部持有比例, 2)}% · ${
          holders.说明 ?? "内部持有为补充披露。"
        }`
      : holders.说明,
    "暂未取得该基金最新持有人结构。",
  );

  text("#purchase-fee-method", purchaseFee.收费方式, "费率暂无");
  if (!feeRows.length) {
    text("#purchase-fee-lead-label", "买入费率");
    text("#purchase-fee-lead", null);
    text(
      "#purchase-fee-note",
      purchaseFee.说明,
      "部分不开放申购或无申购费的基金可能不提供费率表。",
    );
  } else {
    const leadRow = feeRows[0];
    const leadFee = leadRow.天天基金优惠费率 ?? leadRow.原费率 ?? "—";
    text(
      "#purchase-fee-lead-label",
      leadRow.天天基金优惠费率 ? "买入费率 · 天天基金优惠" : "买入费率",
    );
    text("#purchase-fee-lead", leadFee);
    text("#purchase-fee-note", purchaseFee.说明);
  }

  const redeemList = document.querySelector("#redeem-fee-list");
  redeemList.replaceChildren();
  if (!redeemRows.length) {
    const empty = document.createElement("p");
    empty.className = "purchase-fee-empty";
    empty.textContent = "该基金暂无可用的赎回费率表。";
    redeemList.append(empty);
    text(
      "#redeem-fee-note",
      redeemFee.说明,
      "部分基金可能不收取赎回费或未提供分档费率。",
    );
    return;
  }
  redeemRows.forEach((row) => {
    const item = document.createElement("div");
    item.className = "purchase-fee-row";
    const condition = document.createElement("span");
    condition.textContent = row.适用条件 ?? "默认持有期限";
    const rates = document.createElement("div");
    const rate = document.createElement("strong");
    rate.textContent = row.赎回费率 ?? "—";
    rates.append(rate);
    item.append(condition, rates);
    redeemList.append(item);
  });
  text("#redeem-fee-note", redeemFee.说明);
}

function renderFundPeople(basic) {
  const managerData = basic.基金经理 ?? {};
  const managers = managerData.现任 ?? [];
  const historicalManagers = managerData.历史经理 ?? [];
  const managerChanges = managerData.组合变更 ?? [];
  const managerList = document.querySelector("#fund-manager-list");
  managerList.replaceChildren();
  text(
    "#fund-manager-count",
    managers.length ? `${managers.length} 位现任` : null,
    "现任信息暂无",
  );

  if (!managers.length) {
    const empty = document.createElement("p");
    empty.className = "fund-manager-empty";
    empty.textContent = "暂未取得该基金现任经理的详细档案。";
    managerList.append(empty);
  }

  managers.forEach((manager) => {
    const card = document.createElement("article");
    card.className = "fund-manager-person";

    const heading = document.createElement("div");
    heading.className = "fund-manager-person-heading";
    const monogram = document.createElement("span");
    monogram.className = "fund-manager-monogram";
    monogram.textContent = String(manager.姓名 ?? "经理").slice(-2);
    const identity = document.createElement("div");
    const name = document.createElement(manager.详情链接 ? "a" : "strong");
    name.textContent = manager.姓名 ?? "姓名暂无";
    if (manager.详情链接) {
      name.href = manager.详情链接;
      name.target = "_blank";
      name.rel = "noreferrer";
      name.title = `在天天基金查看${manager.姓名 ?? "基金经理"}档案`;
    }
    const scope = document.createElement("small");
    scope.textContent =
      manager.现任基金资产总规模 != null
        ? `现任基金 ${formatNumber(manager.现任基金资产总规模, 2)} 亿元`
        : manager.所属公司 ?? "现任基金资产规模暂无";
    identity.append(name, scope);
    heading.append(monogram, identity);

    const metrics = document.createElement("dl");
    metrics.className = "fund-manager-metrics";
    [
      ["累计从业", manager.从业年限],
      ["本基金任期", manager.本基金任期],
      ["上任日期", manager.上任日期],
      ["任职回报", manager.本基金任职回报],
    ].forEach(([label, value]) => {
      const item = document.createElement("div");
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      term.textContent = label;
      detail.textContent = value ?? "—";
      item.append(term, detail);
      metrics.append(item);
    });
    card.append(heading, metrics);
    managerList.append(card);
  });

  text(
    "#fund-manager-note",
    managers.length
      ? `从业年限采用${managerData.从业口径 ?? "累计基金经理任职时间"}；本基金任期按现任经理逐人统计。`
      : null,
    "经理从业与任期数据来自天天基金经理档案。",
  );

  const historyList = document.querySelector("#fund-manager-history-list");
  historyList.replaceChildren();
  text(
    "#fund-manager-history-count",
    historicalManagers.length ? `${historicalManagers.length} 位` : null,
    "无已离任经理",
  );
  if (!historicalManagers.length) {
    const empty = document.createElement("p");
    empty.className = "fund-manager-history-empty";
    empty.textContent = "公开记录中暂无已离任经理。";
    historyList.append(empty);
  }
  historicalManagers.forEach((manager) => {
    const item = document.createElement("article");
    item.className = "fund-manager-history-person";
    const heading = document.createElement("div");
    const name = document.createElement(manager.详情链接 ? "a" : "strong");
    name.textContent = manager.姓名 ?? "姓名暂无";
    if (manager.详情链接) {
      name.href = manager.详情链接;
      name.target = "_blank";
      name.rel = "noreferrer";
    }
    const count = document.createElement("span");
    count.textContent = `${manager.任职次数 ?? manager.任职区间?.length ?? 1} 段任职`;
    heading.append(name, count);

    const periods = document.createElement("div");
    periods.className = "fund-manager-history-periods";
    (manager.任职区间 ?? []).forEach((period) => {
      const row = document.createElement("p");
      row.textContent = `${period.起始日期 ?? "—"} — ${period.截止日期 ?? "—"}`;
      periods.append(row);
    });
    item.append(heading, periods);
    historyList.append(item);
  });

  const changeList = document.querySelector("#fund-manager-change-list");
  changeList.replaceChildren();
  text(
    "#fund-manager-history-summary",
    historicalManagers.length || managerChanges.length
      ? `${historicalManagers.length} 位历史经理 · ${managerChanges.length} 个组合区间`
      : null,
    "暂无历史记录",
  );
  text(
    "#fund-manager-change-count",
    managerChanges.length ? `${managerChanges.length} 个区间` : null,
    "暂无记录",
  );
  if (!managerChanges.length) {
    const empty = document.createElement("li");
    empty.className = "fund-manager-change-empty";
    empty.textContent = "暂未取得经理组合变更记录。";
    changeList.append(empty);
  }
  managerChanges.forEach((change) => {
    const item = document.createElement("li");
    item.className = `fund-manager-change${change.当前组合 ? " is-current" : ""}`;

    const marker = document.createElement("span");
    marker.className = "fund-manager-change-marker";
    marker.setAttribute("aria-hidden", "true");

    const content = document.createElement("div");
    const meta = document.createElement("div");
    meta.className = "fund-manager-change-meta";
    const period = document.createElement("span");
    period.textContent = `${change.起始日期 ?? "—"} — ${change.截止日期 ?? "—"}`;
    const duration = document.createElement("small");
    duration.textContent = change.任职期间 ?? "任职时长暂无";
    meta.append(period, duration);

    const names = document.createElement("div");
    names.className = "fund-manager-change-names";
    (change.经理 ?? []).forEach((manager, index) => {
      if (index) names.append(document.createTextNode(" · "));
      const name = document.createElement(manager.详情链接 ? "a" : "strong");
      name.textContent = manager.姓名 ?? "姓名暂无";
      if (manager.详情链接) {
        name.href = manager.详情链接;
        name.target = "_blank";
        name.rel = "noreferrer";
      }
      names.append(name);
    });

    const returnValue = document.createElement("span");
    returnValue.className = "fund-manager-change-return";
    returnValue.textContent = `区间回报 ${change.区间回报 ?? "—"}`;
    const numericReturn = Number.parseFloat(change.区间回报);
    if (Number.isFinite(numericReturn)) {
      returnValue.classList.add(numericReturn < 0 ? "is-negative" : "is-positive");
    }
    content.append(meta, names, returnValue);
    item.append(marker, content);
    changeList.append(item);
  });

  const company = basic.基金公司 ?? {};
  text("#fund-company-name", company.名称 ?? basic.管理人);
  text(
    "#fund-company-scale",
    company.管理规模 != null
      ? `${formatNumber(company.管理规模, 2)} 亿元`
      : null,
  );
  text("#fund-company-founded", company.成立日期);
  text("#fund-company-age", company.成立时间);
  text(
    "#fund-company-count",
    company.基金数量 != null ? `${formatNumber(company.基金数量, 0)} 只` : null,
  );
  text(
    "#fund-company-manager-count",
    company.基金经理数量 != null
      ? `${formatNumber(company.基金经理数量, 0)} 人`
      : null,
  );
  text(
    "#fund-company-update",
    company.更新日期 ? `更新 ${company.更新日期}` : null,
    "榜单数据",
  );
}

function renderShareClassAdvice(advice) {
  const card = document.querySelector("#share-class-card");
  if (!advice || !advice.可用) {
    card.hidden = true;
    return;
  }
  card.hidden = false;

  const a = advice.A类 ?? {};
  const c = advice.C类 ?? {};
  const periods = advice.持有期比较 ?? [];
  text(
    "#share-class-current",
    advice.当前份额 ? `当前查看 ${advice.当前份额} 类` : "—",
  );

  const threshold = advice.临界持有天数;
  text(
    "#share-class-threshold",
    periods.length
      ? threshold
        ? `${threshold} 天起 A 类更省`
        : `${periods.length} 个持有区间`
      : "费率数据待补全",
  );
  text("#share-class-summary", advice.建议);

  const redeemTierLabel = (share) => {
    const count = share.赎回费率?.明细?.length ?? 0;
    return count ? `赎回费 ${count} 档` : "赎回费未知";
  };
  const renderFundLink = (selector, share, feeSummary) => {
    const container = document.querySelector(selector);
    container.replaceChildren();
    const code = String(share.代码 ?? "");
    if (!validateCode(code)) {
      container.textContent = `${share.名称 ?? "—"}（${code || "—"}） · ${feeSummary}`;
      return;
    }

    const link = document.createElement("a");
    link.className = "share-class-fund-link";
    link.href = `/?code=${encodeURIComponent(code)}`;
    link.title = `查看 ${share.名称 ?? code}（${code}）`;
    const name = document.createElement("span");
    name.textContent = share.名称 ?? "未命名基金";
    const codeLabel = document.createElement("b");
    codeLabel.textContent = code;
    const arrow = document.createElement("i");
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = "↗";
    link.append(name, codeLabel, arrow);

    const detail = document.createElement("span");
    detail.className = "share-class-fee-summary";
    detail.textContent = feeSummary;
    container.append(link, detail);
  };
  const aRate =
    a.申购费率 != null ? `申购费 ${a.申购费率}%` : "申购费未知";
  const aSales =
    a.年销售服务费率 != null
      ? `服务费 ${a.年销售服务费率}%/年`
      : "服务费未知";
  renderFundLink(
    "#share-class-a",
    a,
    `${aRate} · ${redeemTierLabel(a)} · ${aSales}`,
  );
  const cPurchase =
    c.申购费率 != null ? `申购费 ${c.申购费率}%` : "申购费未知";
  const cSales =
    c.年销售服务费率 != null
      ? `服务费 ${c.年销售服务费率}%/年`
      : "服务费未知";
  renderFundLink(
    "#share-class-c",
    c,
    `${cPurchase} · ${redeemTierLabel(c)} · ${cSales}`,
  );

  const periodsList = document.querySelector("#share-class-periods");
  periodsList.replaceChildren();
  const formatCostRange = (period, share) => {
    const start = Number(period[`${share}总费率起`]);
    const endValue = period[`${share}总费率止`];
    const end = Number(endValue);
    if (!Number.isFinite(start)) return "—";
    if (endValue == null) return `${formatNumber(start, 3)}% 起`;
    if (!Number.isFinite(end) || Math.abs(start - end) < 0.0005) {
      return `${formatNumber(start, 3)}%`;
    }
    return `${formatNumber(start, 3)}–${formatNumber(end, 3)}%`;
  };
  if (!periods.length) {
    const empty = document.createElement("p");
    empty.className = "share-class-period-empty";
    empty.textContent = "申购、赎回或销售服务费数据不足，暂无法分段比较。";
    periodsList.append(empty);
  }
  periods.forEach((period) => {
    const winner = period.更省份额 ?? "相同";
    const row = document.createElement("article");
    row.className = `share-class-period winner-${winner === "相同" ? "tie" : winner.toLowerCase()}`;

    const heading = document.createElement("div");
    heading.className = "share-class-period-label";
    const range = document.createElement("strong");
    range.textContent = period.持有期限 ?? "持有期未知";
    const verdict = document.createElement("span");
    verdict.textContent = winner === "相同" ? "成本接近" : `${winner} 类更省`;
    heading.append(range, verdict);

    const costs = document.createElement("div");
    costs.className = "share-class-period-costs";
    ["A", "C"].forEach((share) => {
      const cost = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = `${share} 类总费率`;
      const value = document.createElement("strong");
      value.textContent = formatCostRange(period, share);
      const breakdown = document.createElement("small");
      breakdown.textContent = `申购 ${formatNumber(period[`${share}申购费率`], 3)}% + 赎回 ${formatNumber(period[`${share}赎回费率`], 3)}%`;
      cost.append(label, value, breakdown);
      costs.append(cost);
    });
    row.append(heading, costs);
    periodsList.append(row);
  });

  text("#share-class-note", advice.说明);
}

function renderFund(data) {
  const basic = data.基础资料 ?? {};
  const performance = data.历史业绩 ?? {};
  const source = data.数据来源 ?? {};

  currentFundSnapshot = {
    code: basic.代码 ?? currentCode,
    name: basic.名称 ?? "",
    fund_type: basic.类型 ?? "",
  };

  document.querySelector(".compact-profile").open = true;
  document.querySelector(".holding-simulator").open = false;

  text("#fund-name", basic.名称);
  text("#fund-code-badge", basic.代码);
  const fundXueqiuLink = document.querySelector("#fund-xueqiu-link");
  const fundXueqiuHref = fundXueqiuUrl(basic.代码);
  fundXueqiuLink.hidden = !fundXueqiuHref;
  fundXueqiuLink.href = fundXueqiuHref || "#";
  fundXueqiuLink.title = fundXueqiuHref
    ? `在雪球查看${basic.名称 ?? "该基金"}`
    : "";
  text("#fund-type", basic.类型);
  text("#fund-date", basic.成立日 ? `成立于 ${basic.成立日}` : "成立日暂无");
  text("#fund-cache-note", dailyCacheLabel(data._缓存));
  refreshButton.disabled = false;
  refreshButton.querySelector("span").textContent = "强制刷新";
  text(
    "#query-time",
    source.查询时间
      ? `查询于 ${new Date(source.查询时间).toLocaleString("zh-CN", {
          hour12: false,
        })}`
      : "查询时间未知",
  );

  text("#manager", basic.管理人);
  text("#custodian", basic.托管人);
  text("#management-fee", basic.管理费率);
  text("#custodian-fee", basic.托管费率);
  text(
    "#sales-service-fee",
    basic.销售服务费率 != null
      ? `${formatNumber(basic.销售服务费率, 3)}%（每年）`
      : null,
  );
  renderShareClassAdvice(basic.AC份额建议);
  text("#benchmark", basic.业绩比较基准);
  document.querySelector("#benchmark").title =
    basic.业绩比较基准 ?? "业绩比较基准暂无";
  text("#data-source", `净值及业绩：${source.净值及业绩 ?? "AKShare"}`);

  renderFundProfile(basic);
  renderFundPeople(basic);
  renderPerformance(performance);
  renderNavHistory(data.净值曲线);
  initializeTrackBenchmark(data.赛道基准建议);
  initializeHoldingsExplorer(data.基金持仓);
  renderWarnings(data.提示);
  syncFavoriteButton();
}

async function queryFund(code, refresh = false) {
  if (!validateCode(code)) {
    showInputError("请输入完整的六位数字基金代码。");
    codeInput.focus();
    return;
  }

  clearInputError();
  holdingsRequestId += 1;
  currentCode = code;
  codeInput.value = code;
  refreshButton.disabled = true;
  refreshButton.querySelector("span").textContent = "刷新中…";
  setView("loading");

  try {
    const params = new URLSearchParams();
    if (refresh) params.set("refresh", "true");
    const response = await fetch(`/api/funds/${code}?${params}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `查询失败（HTTP ${response.status}）`);
    }

    payload._缓存 = {
      状态: response.headers.get("X-Cache"),
      新鲜度: response.headers.get("X-Cache-Status"),
      数据日期: response.headers.get("X-Data-Date"),
      下次更新: response.headers.get("X-Next-Refresh"),
      强制刷新: refresh,
    };
    renderFund(payload);
    recordSearchHistory(code, payload?.基础资料?.名称 ?? "");
    setView("results");
    history.replaceState(null, "", `/?code=${code}`);
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    refreshButton.disabled = false;
    refreshButton.querySelector("span").textContent = "强制刷新";
    errorMessage.textContent = error.message || "未知错误，请稍后重试。";
    setView("error");
  }
}

const SEARCH_HISTORY_COOKIE = "fund_search_history";
const SEARCH_HISTORY_MAX = 12;
const searchHistoryListEl = document.querySelector("#search-history-list");
const searchHistoryEmptyEl = document.querySelector("#search-history-empty");
const searchHistoryClearEl = document.querySelector("#search-history-clear");
const searchHistoryCountEl = document.querySelector("#search-history-count");
const fundSearchDialog = document.querySelector("#fund-search-dialog");
const searchHistoryDialog = document.querySelector("#search-history-dialog");
const fundSearchSuggestionsEl = document.querySelector(
  "#fund-search-suggestions",
);
const fundSearchSuggestionListEl = document.querySelector(
  "#fund-search-suggestion-list",
);
const fundSearchMatchCountEl = document.querySelector(
  "#fund-search-match-count",
);
let fundSearchResults = [];
let fundSearchActiveIndex = -1;
let fundSearchLastQuery = "";
let fundSearchTimer = null;
let fundSearchRequestId = 0;

function hideFundSearchSuggestions() {
  fundSearchSuggestionsEl.hidden = true;
  codeInput.setAttribute("aria-expanded", "false");
  codeInput.removeAttribute("aria-activedescendant");
  fundSearchActiveIndex = -1;
}

function setFundSearchActiveIndex(index) {
  const options = [...fundSearchSuggestionListEl.querySelectorAll("[role='option']")];
  if (!options.length) return;
  fundSearchActiveIndex = (index + options.length) % options.length;
  options.forEach((option, optionIndex) => {
    const active = optionIndex === fundSearchActiveIndex;
    option.classList.toggle("active", active);
    option.setAttribute("aria-selected", String(active));
  });
  const activeOption = options[fundSearchActiveIndex];
  codeInput.setAttribute("aria-activedescendant", activeOption.id);
  activeOption.scrollIntoView({ block: "nearest" });
}

function selectFundSearchResult(item) {
  if (!item?.代码 || !validateCode(item.代码)) return;
  codeInput.value = item.代码;
  hideFundSearchSuggestions();
  fundSearchDialog.close();
  queryFund(item.代码);
}

function renderFundSearchSuggestions(items, total, query) {
  fundSearchResults = items;
  fundSearchLastQuery = query;
  fundSearchSuggestionListEl.replaceChildren();
  fundSearchMatchCountEl.textContent = total > items.length
    ? `显示 ${items.length} / ${total}`
    : `${total} 条匹配`;

  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "fund-search-no-result";
    empty.textContent = "本地目录中没有找到匹配基金";
    fundSearchSuggestionListEl.append(empty);
  } else {
    items.forEach((item, index) => {
      const option = document.createElement("button");
      option.type = "button";
      option.id = `fund-search-option-${index}`;
      option.className = "fund-search-suggestion";
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", "false");

      const order = document.createElement("span");
      order.textContent = String(index + 1).padStart(2, "0");
      const identity = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = item.名称 || "未命名基金";
      const meta = document.createElement("small");
      meta.textContent = `${item.代码} · ${item.类型 || "类型未知"}`;
      identity.append(name, meta);
      const arrow = document.createElement("i");
      arrow.textContent = "↗";
      option.append(order, identity, arrow);
      option.addEventListener("mouseenter", () => setFundSearchActiveIndex(index));
      option.addEventListener("click", () => selectFundSearchResult(item));
      fundSearchSuggestionListEl.append(option);
    });
  }
  fundSearchActiveIndex = -1;
  fundSearchSuggestionsEl.hidden = false;
  codeInput.setAttribute("aria-expanded", "true");
}

async function performFundSearch(query) {
  const normalized = query.trim();
  if (normalized.length < 2) {
    hideFundSearchSuggestions();
    return [];
  }
  const requestId = ++fundSearchRequestId;
  inputHelp.textContent = "正在搜索本地基金目录…";
  try {
    const params = new URLSearchParams({ q: normalized, limit: "10" });
    const payload = await readApiPayload(
      await fetch(`/api/funds/search?${params}`),
    );
    if (requestId !== fundSearchRequestId) return [];
    const items = Array.isArray(payload.基金) ? payload.基金 : [];
    renderFundSearchSuggestions(
      items,
      Number(payload.匹配总数) || items.length,
      normalized,
    );
    inputHelp.textContent = items.length
      ? "选择一只基金，或按回车打开第一条结果"
      : "换一个名称片段或输入六位基金代码";
    return items;
  } catch (error) {
    if (requestId !== fundSearchRequestId) return [];
    hideFundSearchSuggestions();
    showInputError(error.message || "本地基金目录搜索失败");
    return [];
  }
}

function readSearchHistory() {
  const match = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${SEARCH_HISTORY_COOKIE}=`));
  if (!match) return [];
  try {
    const parsed = JSON.parse(decodeURIComponent(match.split("=").slice(1).join("=")));
    return Array.isArray(parsed)
      ? parsed.filter((item) => item && /^\d{6}$/.test(item.code))
      : [];
  } catch (error) {
    return [];
  }
}

function writeSearchHistory(list) {
  const expires = new Date(Date.now() + 180 * 24 * 60 * 60 * 1000).toUTCString();
  const value = encodeURIComponent(JSON.stringify(list.slice(0, SEARCH_HISTORY_MAX)));
  document.cookie = `${SEARCH_HISTORY_COOKIE}=${value}; expires=${expires}; path=/; SameSite=Lax`;
}

function recordSearchHistory(code, name) {
  if (!/^\d{6}$/.test(code)) return;
  const list = readSearchHistory().filter((item) => item.code !== code);
  list.unshift({ code, name: name || "" });
  writeSearchHistory(list);
  renderSearchHistory();
}

function renderSearchHistory() {
  const list = readSearchHistory();
  searchHistoryListEl.innerHTML = "";
  searchHistoryCountEl.textContent = String(list.length);
  const isEmpty = !list.length;
  searchHistoryListEl.hidden = isEmpty;
  searchHistoryEmptyEl.hidden = !isEmpty;
  searchHistoryClearEl.hidden = isEmpty;
  if (isEmpty) return;
  list.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "search-history-item";
    button.dataset.code = item.code;
    button.title = item.name ? `${item.name}（${item.code}）` : item.code;

    const code = document.createElement("span");
    code.className = "history-code";
    code.textContent = item.code;

    const name = document.createElement("span");
    name.className = "history-name";
    name.textContent = item.name || "未命名基金";

    button.append(code, name);
    button.addEventListener("click", () => {
      searchHistoryDialog.close();
      queryFund(item.code);
    });
    searchHistoryListEl.append(button);
  });
}

searchHistoryClearEl.addEventListener("click", () => {
  writeSearchHistory([]);
  renderSearchHistory();
});

renderSearchHistory();

function prefersDedicatedUtilityPage() {
  return (
    window.navigator.standalone === true ||
    window.matchMedia("(max-width: 820px), (pointer: coarse)").matches
  );
}

document.querySelector("#fund-search-open")?.addEventListener("click", () => {
  if (prefersDedicatedUtilityPage()) {
    window.location.assign("/search");
    return;
  }
  if (!fundSearchDialog.open) fundSearchDialog.showModal();
  requestAnimationFrame(() => {
    codeInput.focus();
    codeInput.select();
  });
});

document.querySelector("#fund-search-close")?.addEventListener("click", () => {
  fundSearchDialog.close();
});

fundSearchDialog?.addEventListener("click", (event) => {
  if (event.target === fundSearchDialog) fundSearchDialog.close();
});

fundSearchDialog?.addEventListener("close", () => {
  clearTimeout(fundSearchTimer);
  fundSearchRequestId += 1;
  hideFundSearchSuggestions();
  clearInputError();
});

document.querySelector("#search-history-open")?.addEventListener("click", () => {
  renderSearchHistory();
  if (!searchHistoryDialog.open) searchHistoryDialog.showModal();
});

document
  .querySelector("#search-history-close")
  ?.addEventListener("click", () => searchHistoryDialog.close());

searchHistoryDialog?.addEventListener("click", (event) => {
  if (event.target === searchHistoryDialog) searchHistoryDialog.close();
});

const watchlistDialog = document.querySelector("#watchlist-dialog");
const watchlistListEl = document.querySelector("#watchlist-list");
const watchlistEmptyEl = document.querySelector("#watchlist-empty");
const watchlistTagFiltersEl = document.querySelector("#watchlist-tag-filters");
const watchlistFeedbackEl = document.querySelector("#watchlist-feedback");
const watchlistCountEl = document.querySelector("#watchlist-count");
const watchlistTotalEl = document.querySelector("#watchlist-total");
let watchlistData = { 基金: [], 总数: 0, 标签建议: [] };
let watchlistActiveTag = "全部";

const WATCHLIST_TAG_TONES = new Map([
  ["全部", "all"],
  ["持有中", "holding"],
  ["债基", "bond"],
  ["固收+", "bond"],
  ["偏股", "equity"],
  ["股票", "equity"],
  ["指数", "index"],
  ["成长", "growth"],
  ["价值", "value"],
  ["红利", "dividend"],
  ["低波", "low-risk"],
  ["货币", "cash"],
  ["QDII", "global"],
  ["FOF", "global"],
]);

function watchlistTagTone(tag) {
  const value = String(tag || "");
  const knownTone = WATCHLIST_TAG_TONES.get(value);
  if (knownTone) return knownTone;
  let hash = 0;
  for (const character of value) hash = (hash * 31 + character.codePointAt(0)) >>> 0;
  return `custom-${hash % 4}`;
}

function applyWatchlistTagTone(element, tag) {
  element.dataset.tagTone = watchlistTagTone(tag);
}

function inferWatchlistTypeTag(fundType) {
  const value = String(fundType || "");
  if (/货币/.test(value)) return "货币";
  if (/QDII|海外/.test(value)) return "QDII";
  if (/债|固收/.test(value)) return "债基";
  if (/指数|ETF|联接/.test(value)) return "指数";
  if (/FOF/.test(value)) return "FOF";
  if (/股票|偏股|混合/.test(value)) return "偏股";
  return "其他";
}

function currentWatchlistItem() {
  return (watchlistData.基金 || []).find((item) => item.code === currentCode);
}

function setWatchlistFeedback(message = "", isError = false) {
  watchlistFeedbackEl.textContent = message;
  watchlistFeedbackEl.classList.toggle("error", isError);
}

function syncFavoriteButton() {
  if (!favoriteButton) return;
  const saved = Boolean(currentWatchlistItem());
  favoriteButton.classList.toggle("is-favorite", saved);
  favoriteButton.setAttribute("aria-pressed", String(saved));
  favoriteButton.querySelector("span").textContent = saved ? "已收藏" : "收藏基金";
  favoriteButton.title = saved ? "从收藏移除" : "加入收藏";
}

function applyWatchlistPayload(payload) {
  watchlistData = {
    基金: Array.isArray(payload?.基金) ? payload.基金 : [],
    总数: Number(payload?.总数) || 0,
    标签建议: Array.isArray(payload?.标签建议) ? payload.标签建议 : [],
  };
  watchlistCountEl.textContent = String(watchlistData.总数);
  watchlistTotalEl.textContent = `${watchlistData.总数} FUNDS`;
  syncFavoriteButton();
  renderWatchlist();
}

async function readApiPayload(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `请求失败（HTTP ${response.status}）`);
  }
  return payload;
}

async function loadWatchlist({ quiet = false } = {}) {
  if (!quiet) setWatchlistFeedback("正在读取本地组合…");
  try {
    const payload = await readApiPayload(await fetch("/api/watchlist"));
    applyWatchlistPayload(payload);
    if (!quiet) setWatchlistFeedback("已与本地文件同步");
  } catch (error) {
    setWatchlistFeedback(error.message || "收藏读取失败", true);
  }
}

async function saveWatchlistItem(item, updates = {}) {
  const response = await fetch(`/api/watchlist/${item.code}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: item.name || "",
      fund_type: item.fund_type || "",
      tags: updates.tags ?? item.tags ?? [],
    }),
  });
  return readApiPayload(response);
}

async function removeWatchlistItem(code) {
  return readApiPayload(
    await fetch(`/api/watchlist/${code}`, { method: "DELETE" }),
  );
}

function renderWatchlistTagFilters(items) {
  const counts = new Map();
  items.forEach((item) => {
    (item.tags || []).forEach((tag) => {
      counts.set(tag, (counts.get(tag) || 0) + 1);
    });
  });
  if (watchlistActiveTag !== "全部" && !counts.has(watchlistActiveTag)) {
    watchlistActiveTag = "全部";
  }

  watchlistTagFiltersEl.replaceChildren();
  [["全部", items.length], ...counts.entries()].forEach(([tag, count]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "watchlist-tag-filter";
    applyWatchlistTagTone(button, tag);
    button.classList.toggle("active", tag === watchlistActiveTag);
    button.setAttribute("aria-pressed", String(tag === watchlistActiveTag));

    const name = document.createElement("span");
    name.textContent = tag;
    const total = document.createElement("small");
    total.textContent = String(count).padStart(2, "0");
    button.append(name, total);
    button.addEventListener("click", () => {
      watchlistActiveTag = tag;
      renderWatchlist();
    });
    watchlistTagFiltersEl.append(button);
  });
}

function createWatchlistEditor(item, card) {
  const form = document.createElement("form");
  form.className = "watchlist-editor";
  form.hidden = true;
  let selectedTags = [...new Set((item.tags || []).filter(Boolean))].slice(0, 12);
  let customTagMode = false;

  const heading = document.createElement("div");
  heading.className = "watchlist-editor-heading";
  const headingText = document.createElement("strong");
  headingText.textContent = "管理标签";
  const headingNote = document.createElement("small");
  headingNote.textContent = "最多 12 个";
  heading.append(headingText, headingNote);

  const selected = document.createElement("div");
  selected.className = "watchlist-editor-tags";

  const inputRow = document.createElement("div");
  inputRow.className = "watchlist-tag-input-row";
  inputRow.hidden = true;
  const tagField = document.createElement("label");
  tagField.textContent = "添加自定义标签";
  const tagInput = document.createElement("input");
  tagInput.type = "text";
  tagInput.maxLength = 24;
  tagInput.placeholder = "例如：核心观察";
  tagField.append(tagInput);
  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.textContent = "添加";
  inputRow.append(tagField, addButton);

  const suggestions = document.createElement("div");
  suggestions.className = "watchlist-tag-suggestions";

  const actions = document.createElement("div");
  actions.className = "watchlist-editor-actions";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = "取消";
  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "保存标签";
  actions.append(cancel, save);
  form.append(heading, selected, suggestions, inputRow, actions);

  const hasTag = (tag) =>
    selectedTags.some((current) => current.toLocaleLowerCase() === tag.toLocaleLowerCase());

  function renderTagEditor() {
    selected.replaceChildren();
    if (!selectedTags.length) {
      const empty = document.createElement("span");
      empty.className = "watchlist-tags-empty";
      empty.textContent = "尚未添加标签，保存后会自动补充基金类型标签";
      selected.append(empty);
    } else {
      selectedTags.forEach((tag) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "watchlist-tag removable";
        applyWatchlistTagTone(chip, tag);
        chip.setAttribute("aria-label", `移除标签 ${tag}`);
        chip.textContent = `${tag} ×`;
        chip.addEventListener("click", () => {
          selectedTags = selectedTags.filter((current) => current !== tag);
          renderTagEditor();
        });
        selected.append(chip);
      });
    }

    suggestions.replaceChildren();
    const label = document.createElement("span");
    label.textContent = "从已有标签选择";
    suggestions.append(label);
    (watchlistData.标签建议 || []).forEach((tag) => {
      const choice = document.createElement("button");
      choice.type = "button";
      choice.className = "watchlist-tag-choice";
      applyWatchlistTagTone(choice, tag);
      choice.textContent = tag;
      choice.disabled = hasTag(tag) || selectedTags.length >= 12;
      choice.addEventListener("click", () => {
        if (selectedTags.length < 12 && !hasTag(tag)) selectedTags.push(tag);
        renderTagEditor();
      });
      suggestions.append(choice);
    });

    const custom = document.createElement("button");
    custom.type = "button";
    custom.className = "watchlist-tag-choice custom";
    custom.textContent = customTagMode ? "收起自定义" : "+ 自定义";
    custom.disabled = selectedTags.length >= 12;
    custom.setAttribute("aria-expanded", String(customTagMode));
    custom.addEventListener("click", () => {
      customTagMode = !customTagMode;
      renderTagEditor();
      if (customTagMode) tagInput.focus();
    });
    suggestions.append(custom);
    inputRow.hidden = !customTagMode || selectedTags.length >= 12;
  }

  function addCustomTag() {
    const tag = tagInput.value.trim().replace(/\s+/g, " ");
    if (!tag || selectedTags.length >= 12 || hasTag(tag)) return;
    selectedTags.push(tag);
    tagInput.value = "";
    customTagMode = false;
    renderTagEditor();
  }

  addButton.addEventListener("click", addCustomTag);
  tagInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    addCustomTag();
  });
  renderTagEditor();

  cancel.addEventListener("click", () => {
    form.hidden = true;
    card.classList.remove("editing");
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    save.disabled = true;
    save.textContent = "保存中…";
    try {
      const payload = await saveWatchlistItem(item, {
        tags: selectedTags,
      });
      applyWatchlistPayload(payload);
      setWatchlistFeedback("标签已写入本地文件");
    } catch (error) {
      setWatchlistFeedback(error.message || "保存失败", true);
      save.disabled = false;
      save.textContent = "保存标签";
    }
  });
  return { form, tagInput };
}

function createWatchlistCard(item, index) {
  const card = document.createElement("article");
  card.className = "watchlist-card";

  const main = document.createElement("button");
  main.type = "button";
  main.className = "watchlist-card-main";
  main.title = `打开 ${item.name || item.code}`;

  const order = document.createElement("span");
  order.className = "watchlist-order";
  order.textContent = String(index + 1).padStart(2, "0");

  const identity = document.createElement("span");
  identity.className = "watchlist-identity";
  const displayName = document.createElement("strong");
  displayName.textContent = item.name || "未命名基金";
  const metadata = document.createElement("small");
  metadata.textContent = `${item.code} · ${item.fund_type || "类型未知"}`;
  identity.append(displayName, metadata);

  const tags = document.createElement("span");
  tags.className = "watchlist-tags";
  (item.tags || []).forEach((tag) => {
    const chip = document.createElement("span");
    chip.className = "watchlist-tag";
    applyWatchlistTagTone(chip, tag);
    chip.textContent = tag;
    tags.append(chip);
  });
  main.append(order, identity, tags);
  main.addEventListener("click", () => {
    watchlistDialog.close();
    queryFund(item.code);
  });

  const controls = document.createElement("div");
  controls.className = "watchlist-card-controls";
  const edit = document.createElement("button");
  edit.type = "button";
  edit.textContent = "标签";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "danger";
  remove.textContent = "移除";
  controls.append(edit, remove);

  const { form: editor, tagInput } = createWatchlistEditor(item, card);
  edit.addEventListener("click", () => {
    const opening = editor.hidden;
    document.querySelectorAll(".watchlist-editor").forEach((form) => {
      form.hidden = true;
      form.closest(".watchlist-card")?.classList.remove("editing");
    });
    editor.hidden = !opening;
    card.classList.toggle("editing", opening);
    if (opening) tagInput.focus();
  });
  remove.addEventListener("click", async () => {
    remove.disabled = true;
    remove.textContent = "移除中…";
    try {
      applyWatchlistPayload(await removeWatchlistItem(item.code));
      setWatchlistFeedback(`已移除 ${item.name || item.code}`);
    } catch (error) {
      setWatchlistFeedback(error.message || "移除失败", true);
      remove.disabled = false;
      remove.textContent = "移除";
    }
  });

  card.append(main, controls, editor);
  return card;
}

function renderWatchlist() {
  const items = watchlistData.基金 || [];
  renderWatchlistTagFilters(items);
  const visibleItems =
    watchlistActiveTag === "全部"
      ? items
      : items.filter((item) => (item.tags || []).includes(watchlistActiveTag));
  watchlistListEl.replaceChildren();
  visibleItems.forEach((item, index) => {
    watchlistListEl.append(createWatchlistCard(item, index));
  });
  watchlistEmptyEl.hidden = items.length > 0;
  watchlistListEl.hidden = items.length === 0;
}

document.querySelector("#watchlist-open")?.addEventListener("click", () => {
  if (prefersDedicatedUtilityPage()) {
    window.location.assign("/watchlist");
    return;
  }
  if (!watchlistDialog.open) watchlistDialog.showModal();
  loadWatchlist();
});

document.querySelector("#watchlist-close")?.addEventListener("click", () => {
  watchlistDialog.close();
});

watchlistDialog?.addEventListener("click", (event) => {
  if (event.target === watchlistDialog) watchlistDialog.close();
});

favoriteButton?.addEventListener("click", async () => {
  if (!currentFundSnapshot?.code) return;
  favoriteButton.disabled = true;
  try {
    const saved = currentWatchlistItem();
    const payload = saved
      ? await removeWatchlistItem(currentFundSnapshot.code)
      : await saveWatchlistItem({
          ...currentFundSnapshot,
          tags: [inferWatchlistTypeTag(currentFundSnapshot.fund_type), "持有中"],
        });
    applyWatchlistPayload(payload);
  } catch (error) {
    setWatchlistFeedback(error.message || "收藏操作失败", true);
  } finally {
    favoriteButton.disabled = false;
  }
});

loadWatchlist({ quiet: true });

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearTimeout(fundSearchTimer);
  const query = codeInput.value.trim();
  if (validateCode(query)) {
    hideFundSearchSuggestions();
    fundSearchDialog.close();
    queryFund(query);
    return;
  }
  const selected = fundSearchResults[fundSearchActiveIndex]
    || (fundSearchLastQuery === query ? fundSearchResults[0] : null);
  if (selected) {
    selectFundSearchResult(selected);
    return;
  }
  const results = await performFundSearch(query);
  if (results[0]) {
    selectFundSearchResult(results[0]);
  } else if (query.length < 2) {
    showInputError("请输入至少两个中文字符，或完整的六位基金代码。");
  }
});

codeInput.addEventListener("input", () => {
  clearTimeout(fundSearchTimer);
  clearInputError();
  const query = codeInput.value.trim();
  if (validateCode(query)) {
    inputHelp.textContent = "按回车直接查询此基金代码";
  }
  if (query.length < 2) {
    fundSearchRequestId += 1;
    fundSearchResults = [];
    fundSearchLastQuery = "";
    hideFundSearchSuggestions();
    return;
  }
  fundSearchTimer = setTimeout(() => performFundSearch(query), 180);
});

codeInput.addEventListener("keydown", (event) => {
  if (fundSearchSuggestionsEl.hidden || !fundSearchResults.length) return;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    setFundSearchActiveIndex(fundSearchActiveIndex + 1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    setFundSearchActiveIndex(fundSearchActiveIndex - 1);
  } else if (event.key === "Enter" && fundSearchActiveIndex >= 0) {
    event.preventDefault();
    selectFundSearchResult(fundSearchResults[fundSearchActiveIndex]);
  } else if (event.key === "Escape") {
    hideFundSearchSuggestions();
  }
});

document.querySelectorAll("[data-code]").forEach((button) => {
  button.addEventListener("click", () => queryFund(button.dataset.code));
});

refreshButton.addEventListener("click", () => {
  if (currentCode) queryFund(currentCode, true);
});

const copyAiButton = document.querySelector("#copy-ai-button");
const copyAiButtonLabel = copyAiButton?.querySelector("span");

async function copyAiSummary() {
  if (!currentCode || !copyAiButton) return;
  const originalLabel = copyAiButtonLabel?.textContent ?? "复制给 AI";
  copyAiButton.disabled = true;
  if (copyAiButtonLabel) copyAiButtonLabel.textContent = "生成中…";
  try {
    const response = await fetch(`/api/funds/${currentCode}/ai-summary`);
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `请求失败（${response.status}）`);
    }
    const summary = await response.text();
    await writeToClipboard(summary);
    if (copyAiButtonLabel) copyAiButtonLabel.textContent = "已复制";
  } catch (error) {
    if (copyAiButtonLabel) copyAiButtonLabel.textContent = "复制失败";
    console.error("复制基金摘要失败：", error);
  } finally {
    setTimeout(() => {
      copyAiButton.disabled = false;
      if (copyAiButtonLabel) copyAiButtonLabel.textContent = originalLabel;
    }, 1600);
  }
}

async function writeToClipboard(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "absolute";
  textarea.style.left = "-9999px";
  document.body.append(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

copyAiButton?.addEventListener("click", copyAiSummary);

const fundCodeBadge = document.querySelector("#fund-code-badge");
let fundCodeBadgeResetTimer = null;
fundCodeBadge?.addEventListener("click", async () => {
  const code = fundCodeBadge.textContent?.trim();
  if (!code || !/^\d{6}$/.test(code)) return;
  const original = code;
  try {
    await writeToClipboard(code);
    fundCodeBadge.dataset.copied = "true";
    fundCodeBadge.textContent = "已复制";
  } catch (error) {
    fundCodeBadge.textContent = "复制失败";
    console.error("复制基金代码失败：", error);
  } finally {
    clearTimeout(fundCodeBadgeResetTimer);
    fundCodeBadgeResetTimer = setTimeout(() => {
      fundCodeBadge.textContent = original;
      delete fundCodeBadge.dataset.copied;
    }, 1200);
  }
});

document
  .querySelector("#holdings-quarter-select")
  .addEventListener("change", (event) => {
    queryHoldingsPeriod(event.target.value);
  });

document.querySelectorAll("[data-nav-range]").forEach((button) => {
  button.addEventListener("click", () => {
    showCustomRangeError();
    renderNavChart(button.dataset.navRange);
  });
});

document.querySelectorAll("[data-nav-metric]").forEach((button) => {
  button.addEventListener("click", () =>
    renderNavChart(currentNavRange, button.dataset.navMetric),
  );
});

document.querySelectorAll("[data-periodic-unit]").forEach((button) => {
  button.addEventListener("click", () =>
    renderPeriodicReturns(button.dataset.periodicUnit),
  );
});

const bullBearInfoToggle = document.querySelector("#bull-bear-info-toggle");
const bullBearInfoDialog = document.querySelector("#bull-bear-info-dialog");
bullBearInfoToggle?.addEventListener("click", () => {
  if (!bullBearInfoDialog.open) bullBearInfoDialog.showModal();
});
document
  .querySelector("#bull-bear-info-close")
  ?.addEventListener("click", () => bullBearInfoDialog.close());
bullBearInfoDialog?.addEventListener("click", (event) => {
  if (event.target === bullBearInfoDialog) bullBearInfoDialog.close();
});

document
  .querySelector("#track-benchmark-select")
  .addEventListener("change", (event) => {
    loadTrackBenchmark(event.target.value);
  });

document
  .querySelector("#nav-custom-range")
  .addEventListener("submit", (event) => {
    event.preventDefault();
    const start = document.querySelector("#custom-range-start").value;
    const end = document.querySelector("#custom-range-end").value;
    if (!start || !end) {
      showCustomRangeError("请选择完整的开始和结束日期。");
      return;
    }
    if (start > end) {
      showCustomRangeError("开始日期不能晚于结束日期。");
      return;
    }
    currentCustomRange = { start, end };
    renderNavChart("custom", currentNavMetric);
  });

document
  .querySelector("#holding-simulator-form")
  .addEventListener("submit", (event) => {
    event.preventDefault();
    calculateHoldingSimulation();
  });

document.querySelectorAll("[data-simulator-mode]").forEach((button) => {
  button.addEventListener("click", () =>
    selectInvestmentMode(button.dataset.simulatorMode),
  );
});

const navChart = document.querySelector("#nav-history-chart");
const navTooltip = document.querySelector("#nav-chart-tooltip");
const navChartShell = document.querySelector("#nav-chart-shell");
const navChartMobileQuery = window.matchMedia("(max-width: 700px)");
const handleNavChartBreakpointChange = () => {
  if (Object.keys(currentNavHistory).length) {
    renderNavChart(currentNavRange, currentNavMetric);
  }
};
if (typeof navChartMobileQuery.addEventListener === "function") {
  navChartMobileQuery.addEventListener("change", handleNavChartBreakpointChange);
} else {
  navChartMobileQuery.addListener(handleNavChartBreakpointChange);
}
if ("ResizeObserver" in window) {
  new ResizeObserver(() => positionDrawdownLabels()).observe(navChartShell);
} else {
  window.addEventListener("resize", positionDrawdownLabels);
}
navChart.addEventListener("pointermove", (event) => {
  if (!navPlotPoints.length) return;
  const bounds = navChart.getBoundingClientRect();
  const chartX =
    ((event.clientX - bounds.left) / bounds.width) * navChartDimensions.width;
  const nearest = navPlotPoints.reduce((best, point) =>
    Math.abs(point.x - chartX) < Math.abs(best.x - chartX) ? point : best,
  );
  const crosshair = document.querySelector("#nav-crosshair");
  const [line, circle, benchmarkCircle] = crosshair.children;
  line.setAttribute("x1", nearest.x);
  line.setAttribute("x2", nearest.x);
  circle.setAttribute("cx", nearest.x);
  circle.setAttribute("cy", nearest.y);
  const nearestBenchmark = benchmarkPlotPoints.length
    ? benchmarkPlotPoints.reduce((best, point) =>
        Math.abs(point.x - nearest.x) < Math.abs(best.x - nearest.x)
          ? point
          : best,
      )
    : null;
  if (benchmarkCircle) {
    benchmarkCircle.setAttribute(
      "visibility",
      nearestBenchmark ? "visible" : "hidden",
    );
    if (nearestBenchmark) {
      benchmarkCircle.setAttribute("cx", nearestBenchmark.x);
      benchmarkCircle.setAttribute("cy", nearestBenchmark.y);
    }
  }
  crosshair.setAttribute("visibility", "visible");

  navTooltip.querySelector("span").textContent = formatChartDate(nearest.日期);
  navTooltip.querySelector("strong").textContent =
    currentNavMetric === "回撤修复"
      ? `基金回撤 ${formatPercent(nearest.回撤)}${
          nearestBenchmark
            ? ` · ${currentTrackBenchmark?.简称 ?? "赛道"}回撤 ${formatPercent(
                nearestBenchmark.回撤,
              )}`
            : ""
        }`
      : currentNavMetric === "累计收益率" && nearestBenchmark
        ? `基金 ${formatPercent(nearest.value)} · ${
            currentTrackBenchmark?.简称 ?? "赛道"
          } ${formatPercent(nearestBenchmark.value)}`
      : `${navMetricConfig[currentNavMetric].tooltipLabel} ${formatNavValue(
          nearest.value,
          currentNavMetric,
        )}`;
  navTooltip.style.left = `${
    (nearest.x / navChartDimensions.width) * bounds.width
  }px`;
  navTooltip.style.top = `${
    (nearest.y / navChartDimensions.height) * bounds.height
  }px`;
  navTooltip.classList.toggle(
    "align-right",
    nearest.x > navChartDimensions.width * 0.82,
  );
  navTooltip.hidden = false;
});

navChart.addEventListener("pointerleave", () => {
  navTooltip.hidden = true;
  document
    .querySelector("#nav-crosshair")
    ?.setAttribute("visibility", "hidden");
});

document.querySelectorAll("[data-stock-range]").forEach((button) => {
  button.addEventListener("click", () =>
    renderStockPriceChart(button.dataset.stockRange),
  );
});

const bondStructureHelpDialog = document.querySelector(
  "#bond-structure-help-dialog",
);
const bondStructureHelpSheet = bondStructureHelpDialog.querySelector(
  ".bond-structure-help-sheet",
);

function openBondStructureHelp(name, dimension, weight) {
  const guide = bondStructureGuideCatalog[name] ?? {
    tone: "other",
    introduction: `${name}是本期报告披露的债券分类，当前知识库尚未提供更细的标准化定义。`,
    features: "具体特征需结合原始季报、底层债券名称、发行人和条款判断。",
    return: "取决于实际底层债券的票息、期限、信用利差和市场价格变化。",
    risk: "分类信息不足可能掩盖信用、利率、流动性或特殊条款风险。",
    watch: "优先查看原始季报及底层证券的发行文件、评级与交易信息。",
    riskLevel: "不确定 · 需进一步识别",
    portfolio: "应穿透实际持仓后再判断该类别对组合收益和风险的影响。",
  };
  const normalizedWeight = Number(weight) || 0;
  const dimensionLabel = dimension === "信用属性" ? "信用属性" : "债券品种";

  bondStructureHelpDialog.dataset.tone = guide.tone;
  text(
    "#bond-guide-eyebrow",
    dimension === "信用属性"
      ? "CREDIT PROFILE FIELD GUIDE / 信用属性说明"
      : "BOND TYPE FIELD GUIDE / 债券品种说明",
  );
  text("#bond-structure-help-title", name);
  text("#bond-guide-introduction", guide.introduction);
  text("#bond-guide-weight", `${formatNumber(normalizedWeight, 2)}%`);
  text("#bond-guide-dimension", dimensionLabel);
  text("#bond-guide-features", guide.features);
  text("#bond-guide-return", guide.return);
  text("#bond-guide-risk", guide.risk);
  text("#bond-guide-watch", guide.watch);
  text("#bond-guide-risk-level", guide.riskLevel);
  text(
    "#bond-guide-portfolio",
    `${name}本期占基金净值 ${formatNumber(normalizedWeight, 2)}%。${guide.portfolio}`,
  );

  if (!bondStructureHelpDialog.open) bondStructureHelpDialog.showModal();
  bondStructureHelpSheet.scrollTo({ top: 0, behavior: "auto" });
}

document
  .querySelector("#bond-structure-help-close")
  .addEventListener("click", () => bondStructureHelpDialog.close());

bondStructureHelpDialog.addEventListener("click", (event) => {
  if (event.target === bondStructureHelpDialog) {
    bondStructureHelpDialog.close();
  }
});

const metricHelpDialog = document.querySelector("#metric-help-dialog");
const metricHelpSheet = document.querySelector(".metric-help-sheet");

function openMetricHelp(metric) {
  const target = document.querySelector(
    `[data-metric-help-card="${metric}"]`,
  );
  if (!target) return;
  const alreadyOpen = metricHelpDialog.open;
  document.querySelectorAll("[data-metric-help-card]").forEach((card) => {
    card.classList.toggle("active", card === target);
  });
  metricHelpDialog
    .querySelectorAll(".metric-help-nav [data-metric-help]")
    .forEach((button) => {
      const active = button.dataset.metricHelp === metric;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "true" : "false");
    });
  if (!alreadyOpen) metricHelpDialog.showModal();
  requestAnimationFrame(() => {
    metricHelpSheet.scrollTo({
      top: Math.max(target.offsetTop - 16, 0),
      behavior: alreadyOpen ? "smooth" : "auto",
    });
  });
}

document.querySelectorAll("[data-metric-help]").forEach((button) => {
  button.addEventListener("click", () =>
    openMetricHelp(button.dataset.metricHelp),
  );
});

document
  .querySelector("#metric-help-close")
  .addEventListener("click", () => metricHelpDialog.close());

metricHelpDialog.addEventListener("click", (event) => {
  if (event.target === metricHelpDialog) metricHelpDialog.close();
});

const benchmarkHelpDialog = document.querySelector("#benchmark-help-dialog");
const benchmarkHelpSheet = benchmarkHelpDialog.querySelector(
  ".metric-help-sheet",
);
const benchmarkHelpNav = document.querySelector("#benchmark-help-nav");
const benchmarkHelpContent = document.querySelector("#benchmark-help-content");
let benchmarkCatalogPromise = null;
let benchmarkHelpRendered = false;

function loadBenchmarkCatalog() {
  if (!benchmarkCatalogPromise) {
    benchmarkCatalogPromise = fetch("/api/benchmarks")
      .then((response) => {
        if (!response.ok) throw new Error("赛道基准目录加载失败");
        return response.json();
      })
      .then((data) => data.基准 || [])
      .catch((error) => {
        benchmarkCatalogPromise = null;
        throw error;
      });
  }
  return benchmarkCatalogPromise;
}

// 页面加载即填充下拉框，避免查询基金前下拉框为空。
ensureBenchmarkSelectPopulated().catch(() => {});

function renderBenchmarkHelp(catalog) {
  benchmarkHelpNav.replaceChildren();
  benchmarkHelpContent.replaceChildren();
  catalog.forEach((item, index) => {
    const navButton = document.createElement("button");
    navButton.type = "button";
    navButton.dataset.benchmarkHelp = item.key;
    navButton.textContent = item.简称 || item.名称;
    navButton.addEventListener("click", () => focusBenchmarkHelp(item.key));
    benchmarkHelpNav.append(navButton);

    const article = document.createElement("article");
    article.dataset.benchmarkHelpCard = item.key;

    const header = document.createElement("header");
    const order = document.createElement("span");
    const codeLabel = item.指数代码 ? ` / ${item.指数代码}` : "";
    order.textContent = `${String(index + 1).padStart(2, "0")}${codeLabel}`;
    const headerBody = document.createElement("div");
    const title = document.createElement("h3");
    title.textContent = item.名称;
    const subtitle = document.createElement("p");
    subtitle.textContent = item.类型 || item.说明 || "";
    headerBody.append(title, subtitle);
    header.append(order, headerBody);

    const list = document.createElement("dl");
    [
      ["指数编制", item.编制],
      ["代表含义", item.代表],
      ["适用基金", item.适用],
    ].forEach(([term, detail]) => {
      if (!detail) return;
      const cell = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      dd.textContent = detail;
      cell.append(dt, dd);
      list.append(cell);
    });

    article.append(header, list);
    benchmarkHelpContent.append(article);
  });
  benchmarkHelpRendered = true;
}

function focusBenchmarkHelp(key) {
  const target = benchmarkHelpContent.querySelector(
    `[data-benchmark-help-card="${key}"]`,
  );
  benchmarkHelpContent
    .querySelectorAll("[data-benchmark-help-card]")
    .forEach((card) => card.classList.toggle("active", card === target));
  benchmarkHelpNav
    .querySelectorAll("[data-benchmark-help]")
    .forEach((button) => {
      const active = button.dataset.benchmarkHelp === key;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "true" : "false");
    });
  if (target) {
    requestAnimationFrame(() => {
      benchmarkHelpSheet.scrollTo({
        top: Math.max(target.offsetTop - 16, 0),
        behavior: benchmarkHelpDialog.open ? "smooth" : "auto",
      });
    });
  }
}

async function openBenchmarkHelp() {
  try {
    if (!benchmarkHelpRendered) {
      renderBenchmarkHelp(await loadBenchmarkCatalog());
    }
  } catch (error) {
    benchmarkHelpContent.replaceChildren();
    const notice = document.createElement("p");
    notice.style.padding = "34px 0";
    notice.textContent = error.message || "赛道基准说明暂不可用。";
    benchmarkHelpContent.append(notice);
  }
  if (!benchmarkHelpDialog.open) benchmarkHelpDialog.showModal();
  focusBenchmarkHelp(currentTrackBenchmarkKey || "hs300");
}

document
  .querySelector("#track-benchmark-help")
  .addEventListener("click", openBenchmarkHelp);

document
  .querySelector("#benchmark-help-close")
  .addEventListener("click", () => benchmarkHelpDialog.close());

benchmarkHelpDialog.addEventListener("click", (event) => {
  if (event.target === benchmarkHelpDialog) benchmarkHelpDialog.close();
});

const stockDialog = document.querySelector("#stock-detail-dialog");
const stockChart = document.querySelector("#stock-price-chart");
const stockTooltip = document.querySelector("#stock-chart-tooltip");

function closeStockDetail() {
  stockDetailRequestId += 1;
  if (stockDialog.open) stockDialog.close();
}

document
  .querySelector("#stock-detail-close")
  .addEventListener("click", closeStockDetail);

document
  .querySelector("#stock-detail-refresh")
  .addEventListener("click", () => {
    if (currentStockCode) {
      openStockDetail(
        currentStockCode,
        currentStockFallback,
        true,
      );
    }
  });

stockDialog.addEventListener("click", (event) => {
  if (event.target === stockDialog) closeStockDetail();
});

stockDialog.addEventListener("cancel", () => {
  stockDetailRequestId += 1;
});

stockChart.addEventListener("pointermove", (event) => {
  if (!stockPlotPoints.length) return;
  const bounds = stockChart.getBoundingClientRect();
  const chartX = ((event.clientX - bounds.left) / bounds.width) * 1000;
  const nearest = stockPlotPoints.reduce((best, point) =>
    Math.abs(point.x - chartX) < Math.abs(best.x - chartX) ? point : best,
  );
  const crosshair = document.querySelector("#stock-price-crosshair");
  const [line, circle] = crosshair.children;
  line.setAttribute("x1", nearest.x);
  line.setAttribute("x2", nearest.x);
  circle.setAttribute("cx", nearest.x);
  circle.setAttribute("cy", nearest.y);
  crosshair.setAttribute("visibility", "visible");
  stockTooltip.querySelector("span").textContent = formatChartDate(
    nearest.日期,
  );
  stockTooltip.querySelector("strong").textContent =
    `收盘 ${formatNumber(nearest.value, 2)} 元`;
  stockTooltip.style.left = `${(nearest.x / 1000) * bounds.width}px`;
  stockTooltip.style.top = `${(nearest.y / 340) * bounds.height}px`;
  stockTooltip.classList.toggle("align-right", nearest.x > 820);
  stockTooltip.hidden = false;
});

stockChart.addEventListener("pointerleave", () => {
  stockTooltip.hidden = true;
  document
    .querySelector("#stock-price-crosshair")
    ?.setAttribute("visibility", "hidden");
});

const initialCode = new URLSearchParams(location.search).get("code");
if (initialCode && validateCode(initialCode)) {
  codeInput.value = initialCode;
  queryFund(initialCode);
}
