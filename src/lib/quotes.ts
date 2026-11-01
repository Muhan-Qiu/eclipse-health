/**
 * 每日健康名言。
 *
 * 选题标准：真实、广泛流传、出处可核实的健康/照护/生活方式句子。
 * 署名存疑的一律记为「佚名 / Anonymous」，不编造作者与出处；`source` 仅用于核对，不展示。
 * 选择规则：按本地日期的 dayOfYear % 30 取当天一条，同一天多次进入结果不变。
 */
export interface HealthQuote {
  /** 中文正文 */
  zh: string;
  /** 英文正文 */
  en: string;
  /** 中文署名 */
  author: string;
  /** 英文署名 */
  authorEn: string;
  /** 可核实出处（仅作核对，不展示） */
  source?: string;
}

export const QUOTES: readonly HealthQuote[] = [
  {
    zh: "生命短暂，医术长存；时机易逝，经验难凭，判断艰难。",
    en: "Life is short, the art long, opportunity fleeting, experience treacherous, judgment difficult.",
    author: "希波克拉底",
    authorEn: "Hippocrates",
    source: "Aphorisms, I.1",
  },
  {
    zh: "哪里有对医术的热爱，哪里就有对人类的爱。",
    en: "Wherever the art of medicine is loved, there is also a love of humanity.",
    author: "希波克拉底",
    authorEn: "Hippocrates",
    source: "Precepts",
  },
  {
    zh: "若能给每个人适量的营养与运动，不多也不少，我们就找到了最稳妥的健康之道。",
    en: "If we could give every individual the right amount of nourishment and exercise, not too little and not too much, we would have found the safest way to health.",
    author: "希波克拉底",
    authorEn: "Hippocrates",
    source: "Attributed to Hippocrates",
  },
  {
    zh: "健康是最大的礼物，知足是最大的财富，信赖是最好的关系。",
    en: "Health is the greatest gift, contentment the greatest wealth, faithfulness the best relationship.",
    author: "佛陀",
    authorEn: "The Buddha",
    source: "Dhammapada 204",
  },
  {
    zh: "护理的目标，是让病人处于最佳状态，好让自然的力量发挥作用。",
    en: "The goal of nursing is to put the patient in the best condition for nature to act upon him.",
    author: "弗洛伦斯·南丁格尔",
    authorEn: "Florence Nightingale",
    source: "Notes on Nursing (1859)",
  },
  {
    zh: "医学是一门关于不确定性的科学，也是一门关于概率的艺术。",
    en: "Medicine is a science of uncertainty and an art of probability.",
    author: "威廉·奥斯勒",
    authorEn: "William Osler",
  },
  {
    zh: "不读书而研究疾病现象，如同在无海图的海上航行；只读书而不接触病人，则根本没有出海。",
    en: "To study the phenomena of disease without books is to sail an uncharted sea, while to study books without patients is not to go to sea at all.",
    author: "威廉·奥斯勒",
    authorEn: "William Osler",
  },
  {
    zh: "健康是身体、精神与社会适应的完好状态，而不仅仅是没有疾病或虚弱。",
    en: "Health is a state of complete physical, mental and social well-being and not merely the absence of disease or infirmity.",
    author: "世界卫生组织",
    authorEn: "World Health Organization",
    source: "WHO Constitution (1948)",
  },
  {
    zh: "享有可达到的最高健康标准，是每个人的基本权利之一。",
    en: "The enjoyment of the highest attainable standard of health is one of the fundamental rights of every human being.",
    author: "世界卫生组织",
    authorEn: "World Health Organization",
    source: "WHO Constitution (1948)",
  },
  {
    zh: "每天一苹果，医生远离我。",
    en: "An apple a day keeps the doctor away.",
    author: "佚名",
    authorEn: "Anonymous",
    source: "English proverb",
  },
  {
    zh: "预防胜于治疗。",
    en: "Prevention is better than cure.",
    author: "佚名",
    authorEn: "Anonymous",
    source: "Proverb",
  },
  {
    zh: "一分预防，胜过十分治疗。",
    en: "An ounce of prevention is worth a pound of cure.",
    author: "本杰明·富兰克林",
    authorEn: "Benjamin Franklin",
    source: "Pennsylvania Gazette (1736)",
  },
  {
    zh: "早睡早起，使人健康、富有而明智。",
    en: "Early to bed and early to rise makes a man healthy, wealthy and wise.",
    author: "佚名",
    authorEn: "Anonymous",
    source: "Traditional proverb",
  },
  {
    zh: "健康是第一财富。",
    en: "The first wealth is health.",
    author: "拉尔夫·沃尔多·爱默生",
    authorEn: "Ralph Waldo Emerson",
    source: "Power, The Conduct of Life",
  },
  {
    zh: "人只有在生病时，才懂得健康的可贵。",
    en: "Health is not valued till sickness comes.",
    author: "托马斯·富勒",
    authorEn: "Thomas Fuller",
    source: "Gnomologia (1732)",
  },
  {
    zh: "一切幸福的根基是健康。",
    en: "The groundwork of all happiness is health.",
    author: "利·亨特",
    authorEn: "Leigh Hunt",
  },
  {
    zh: "愉快的心情最能促进健康，它对心灵和身体同样友善。",
    en: "Cheerfulness is the best promoter of health and is as friendly to the mind as to the body.",
    author: "约瑟夫·艾迪生",
    authorEn: "Joseph Addison",
    source: "The Spectator",
  },
  {
    zh: "步行是最好的运动。养成走远路的习惯。",
    en: "Walking is the best possible exercise. Habituate yourself to walk very far.",
    author: "托马斯·杰斐逊",
    authorEn: "Thomas Jefferson",
    source: "Letter to Peter Carr (1785)",
  },
  {
    zh: "对一个不快乐但身体健康的人来说，一次有力的五英里步行，比世上所有药物和心理学都更有益。",
    en: "A vigorous five-mile walk will do more good for an unhappy but otherwise healthy adult than all the medicine and psychology in the world.",
    author: "保罗·达德利·怀特",
    authorEn: "Paul Dudley White",
  },
  {
    zh: "休息不是懒散。夏日里躺在树下草地上，听水声潺潺，看云朵飘过天空，绝非浪费时间。",
    en: "Rest is not idleness, and to lie sometimes on the grass under trees on a summer's day, listening to the murmur of the water, or watching the clouds float across the sky, is by no means a waste of time.",
    author: "约翰·卢伯克",
    authorEn: "John Lubbock",
    source: "The Use of Life",
  },
  {
    zh: "让土地休息吧；休耕过的田野会给出丰盛的收成。",
    en: "Take rest; a field that has rested gives a bountiful crop.",
    author: "奥维德",
    authorEn: "Ovid",
  },
  {
    zh: "未来的医生不再只开药，而是引导病人关照自己的身体、饮食，以及疾病的成因与预防。",
    en: "The doctor of the future will give no medicine, but will interest his patients in the care of the human frame, in diet and in the cause and prevention of disease.",
    author: "托马斯·爱迪生",
    authorEn: "Thomas Edison",
  },
  {
    zh: "医术之道，在于让病人安心等待，而由自然完成治愈。",
    en: "The art of medicine consists of amusing the patient while nature cures the disease.",
    author: "伏尔泰",
    authorEn: "Voltaire",
  },
  {
    zh: "笑是最好的良药。",
    en: "Laughter is the best medicine.",
    author: "佚名",
    authorEn: "Anonymous",
    source: "Proverb",
  },
  {
    zh: "开怀大笑与充足睡眠，是医生手册里最好的两味药。",
    en: "A good laugh and a long sleep are the best cures in the doctor's book.",
    author: "佚名",
    authorEn: "Anonymous",
    source: "Irish proverb",
  },
  {
    zh: "心安则体健。",
    en: "When the heart is at ease, the body is healthy.",
    author: "佚名",
    authorEn: "Anonymous",
    source: "Chinese proverb",
  },
  {
    zh: "照顾好自己的身体，因为那是你唯一必须居住的地方。",
    en: "Take care of your body. It's the only place you have to live.",
    author: "吉姆·罗恩",
    authorEn: "Jim Rohn",
  },
  {
    zh: "在绝望与希望之间，最好的桥梁是一夜好眠。",
    en: "The best bridge between despair and hope is a good night's sleep.",
    author: "E·约瑟夫·科斯曼",
    authorEn: "E. Joseph Cossman",
  },
  {
    zh: "健康之中有自由。健康是一切自由之首。",
    en: "In health there is freedom. Health is the first of all liberties.",
    author: "亨利·弗雷德里克·阿米尔",
    authorEn: "Henri-Frédéric Amiel",
  },
  {
    zh: "求愈的愿望，本身就是健康的一半。",
    en: "The wish for healing has always been half of health.",
    author: "塞涅卡",
    authorEn: "Seneca",
  },
];

/** 本地日期在当年的第几天（1–366），按本地年月日算，避免夏令时让天数偏移。 */
export function dayOfYear(date: Date): number {
  const start = Date.UTC(date.getFullYear(), 0, 1);
  const current = Date.UTC(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
  );
  return Math.floor((current - start) / 86_400_000) + 1;
}

/** 当天名言：dayOfYear % 30，同一天多次调用结果一致，跨天轮换。 */
export function quoteOfDay(date: Date = new Date()): HealthQuote {
  return QUOTES[dayOfYear(date) % QUOTES.length];
}
