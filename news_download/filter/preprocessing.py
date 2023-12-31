import pymorphy2
import re
import nltk
from nltk.corpus import stopwords

list_words = [
    'telegram',
    'twitter',
    'аборт',
    'аварийный',
    'авербух',
    'автовладелец',
    'аномалия',
    'атмосферный',
    'беженец',
    'бренд',
    'вдова',
    'великий',
    'вера',
    'ветеран',
    'взрыв',
    'внук',
    'возгорание',
    'ворота',
    'вратарь',
    'выборы',
    'гагарин',
    'геноцид',
    'гибель',
    'гитлер',
    'голевой',
    'гололедица',
    'госпитализировать',
    'группировка',
    'губернатор',
    'девушка',
    'диверсия',
    'дождь',
    'древний',
    'жена',
    'жених',
    'забитый',
    'загореться',
    'задержание',
    'заложник',
    'заморозок',
    'захоронение',
    'землетрясение',
    'зритель',
    'изнасиловать',
    'иммигрант',
    'инвалидность',
    'каникулы',
    'кафедра',
    'кафедральный',
    'кибермошенник',
    'кибермошенничество',
    'кинотеатр',
    'кладбище',
    'климат',
    'комик',
    'комикс',
    'концерт',
    'кпрф',
    'ледяной',
    'ленинский',
    'летальный',
    'локализовать',
    'магазин',
    'маникюр',
    'маньяк',
    'материнский',
    'матч',
    'митинг',
    'многодетный',
    'мобилизация',
    'мобилизация',
    'мошенник',
    'мошенничество',
    'мчс',
    'нхл',
    'нога',
    'обстрел',
    'обстрелять',
    'оползень',
    'осадки',
    'паводковый',
    'паводок',
    'пациент',
    'пенсионер',
    'пенсия',
    'плен',
    'погибнуть',
    'подельник',
    'пожар',
    'полицейский',
    'полиция',
    'полуфинал',
    'посёлок',
    'похищение',
    'праздничный',
    'препдриниматель',
    'преступник',
    'развлекательный',
    'реабилитация',
    'ребёнок',
    'режиссёр',
    'родственник',
    'рсзый',
    'самовар',
    'свадьба',
    'семья',
    'синоптик',
    'сирота',
    'скончаться',
    'следственный',
    'смерть',
    'снег',
    'снежный',
    'собеседник',
    'сожитель',
    'соотечественник',
    'соцсеть',
    'студенческий',
    'супруг',
    'телеграм',
    'теракт',
    'терроризм',
    'террористический',
    'убийство',
    'убитый',
    'уголовный',
    'челюсть'
    'фашист',
    'фильм',
    'футбол',
    'футболист',
    'футбольный',
    'хоккеист',
    'хоккейный',
    'храбровый',
    'цветение',
    'церемония',
    'часовой',
    'чемпионат',
    'шайба',
    'школьник',
    'штамм',
    'эвакуировать',
    'эвтаназия',
    'тюрьма',
    'священнослужитель',
    'разврат',
    'священник',
    'бригада',
    'артиллерийский',
    'атака',
    'атаковать',
    'военнопленный',
    'воевать',
    'демилитаризация',
    'десантно-штурмовой',
    'диверсионный',
    'доброволец',
    'контрнаступление',
    'минирование',
    'обстрел',
    'огневой',
    'подбить',
    'укрепрайон',
    'укронацист',
    'эшелон',
    'мятеж',
    'вагнер',
    'please',
    'coach',
    'fans',
    'football',
    'playing',
    'baseball',
    'draft',
    'postseason',
    'sports',
    'blizzard',
    'desantis',
    'election',
    'abortion',
    'elections',
    'legislative',
    'interview',
    'mothers',
    'violence',
    'gunfire',
    'protests',
    'killed',
    'crime',
    'shooting',
    'police',
    'socialist',
    'holocaust',
    'migrants',
    'migration',
    'injured',
    'explosion',
    'ceasefire',
    'soccer',
    'athletes',
    'cloudy',
    'drought',
    'rainfall',
    'rains',
    'witnesses',
    'cartoons',
    'christian',
    'drills',
    'baggage',
    'santos',
    'brooklyn',
    'tsunami',
    'civilians',
    'attack',
    'attacks',
    'mosque',
    'muslims',
    'worship',
    'worshippers',
    'evacuation',
    'rescue',
    'evacuate',
    'polling',
    'stocks',
    'stock ',
    'wife',
    'mother',
    'died',
    'daughter',
    'death',
    'cult',
    'marriage',
    'married',
    'rewards',
    'knight',
    'dame',
    'bakhmut',
    'church',
    'religious',
    'pope',
    'vatican',
    'catholic',
    'pastor',
    'bishops',
    'prayer',
    'prayers',
    'congregation',
    'bishop ',
    'orthodox',
    'priests',
    'spiritual',
    'suicide',
    'sexual',
    'sex ',
    'sexually',
    'abusive',
    'sexuality',
    'raped',
    'survivors',
    'actor',
    'music',
    'artists',
    'prisoner',
    'funeral',
    'burial',
    'mourners',
    'museum',
    'homicides',
    'extradition',
    'deaths',
    'kidnapped',
    'father',
    'son',
    'love',
    'cultural',
    'transgender',
    'identity',
    'wounded',
    'personel',
    'lgbt',
    'policing',
    'jesus',
    'holy',
    'tucker',
    'presidential',
    'tournament',
    'mafia',
    'killing',
    'shooting',
    'cocaine',
    'prigozhin',
    'bloodshed',
    'buried',
    'injured',
    'injuries',
    'missile',
    'wounded',
    'comedy',
    'murderer',
    'literature',
    'bookmakers',
    'ramadan',
    'mosques',
    'explainer',
    'bible',
    'portrait',
    'drummer',
    'pizza',
    'museum',
    'cricket',
    'baseball',
    'championship',
    'filmmaker',
    'musician',
    'acrobats',
    'bicyclist',
    'horseracing',
    'incarceration',
    'gwyneth',
    'tornadoes',
    'cyclone',
    'cleric',
    'shakespeare',
    'rebellion',
    'riot',
    'insurgency',
    'mutiny',
    'wagner',  
]

nltk.download('stopwords')
# stopwords = nltk.download('stopwords')

morph = pymorphy2.MorphAnalyzer()


words_regex = re.compile('\w+')


def find_words(text, regex=words_regex):
    tokens = regex.findall(text.lower())
    return [w for w in tokens if w.isalpha() and len(w) >= 3]


stopwords_list = stopwords.words('russian') + stopwords.words('english')


def lemmatize(words, lemmer=morph, stopwords=stopwords_list):
    lemmas = [lemmer.parse(w)[0].normal_form for w in words]
    return [w for w in lemmas if not w in stopwords
            and w.isalpha()]


def preprocess(text):
    return (lemmatize(find_words(text)))

def check_stop_words(title, words=list_words):
    title = set(preprocess(title))
    if title.intersection(set(words)):
        return False
    return True
