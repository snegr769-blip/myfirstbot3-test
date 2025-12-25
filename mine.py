import random
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from enum import Enum

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Настройки бота
TOKEN = "8295186173:AAHkdN2iZOcwLHwu2ItXjYE0ulG_iSdmFo4"

# Константы
COINS_PER_WIN = 5
DATA_FILE = "duel_data.json"

# Константы для монстров
MONSTER_DIFFICULTIES = {
    "common": {
        "names": ["Зомби", "Скелет", "Слизень"],
        "spawn_chance": 50.0,
        "base_accuracy": 5,
        "max_accuracy": 25,
        "base_dodge": 2,
        "max_dodge": 25,
        "attack_chance": 50,
        "accuracy_boost_chance": 25,
        "dodge_boost_chance": 25,
        "coin_reward": (50, 100)
    },
    "rare": {
        "names": ["Огр", "Мирмеколеон", "Черт"],
        "spawn_chance": 35.5,
        "base_accuracy": 10,
        "max_accuracy": 40,
        "base_dodge": 10,
        "max_dodge": 30,
        "attack_chance": 55,
        "accuracy_boost_chance": 20,
        "dodge_boost_chance": 25,
        "steal_life_chance": 5,  # 1/20 = 5%
        "coin_reward": (100, 200)
    },
    "mythic": {
        "names": ["Грифон", "Виверна", "Косматый", "Василиск"],
        "spawn_chance": 13.5,
        "base_accuracy": 25,
        "max_accuracy": 50,
        "base_dodge": 25,
        "max_dodge": 50,
        "attack_chance": 60,
        "accuracy_boost_chance": 15,
        "dodge_boost_chance": 15,
        "knockdown_chance": 10,  # 1/10 = 10%
        "coin_reward": (200, 400)
    },
    "legendary": {
        "names": ["Дракон", "Аваддон", "Вельзевул"],
        "spawn_chance": 0.5,
        "base_accuracy": 50,
        "max_accuracy": 90,
        "base_dodge": 50,
        "max_dodge": 90,
        "attack_chance": 70,
        "accuracy_boost_chance": 20,
        "dodge_boost_chance": 10,
        "steal_life_chance": 10,  # 1/10 = 10%
        "coin_reward": (500, 1000)
    },
    "treasure": {
        "spawn_chance": 0.5,
        "coin_reward": (100, 300)
    }
}

# Состояния магазина
class ShopState(Enum):
    MAIN = "shop_main"
    PISTOLS = "shop_pistols"
    BOWS = "shop_bows"
    STAFFS = "shop_staffs"
    MELEE = "shop_melee"
    SPECIAL = "shop_special"
    CONFIRM = "shop_confirm"


# Класс для хранения данных пользователей
class UserData:
    def __init__(self):
        self.coins = 0
        self.win_streak = 0
        self.max_win_streak = 0
        self.total_wins = 0
        self.total_losses = 0
        self.weapons = ["standard_musket"]  # Начинаем со стандартного мушкета
        self.current_weapon = "standard_musket"
        self.purchases = {}
        self.monster_kills = {
            "common": 0,
            "rare": 0,
            "mythic": 0,
            "legendary": 0,
            "treasure": 0
        }


# Класс для монстров
class Monster:
    def __init__(self, difficulty: str):
        self.difficulty = difficulty
        self.config = MONSTER_DIFFICULTIES[difficulty]
        
        if difficulty == "treasure":
            self.name = "Клад"
        else:
            self.name = random.choice(self.config["names"])
            
        self.accuracy = self.config.get("base_accuracy", 0)
        self.dodge = self.config.get("base_dodge", 0)
        self.lives = 1
        self.is_dodge_boosted = False
        self.is_accuracy_boosted = False
        self.has_extra_life = False
        self.knockdown_cooldown = False


# Глобальные хранилища данных
class DataStore:
    def __init__(self):
        self.user_data: Dict[int, UserData] = {}
        self.load_data()

    def load_data(self):
        """Загружает данные из файла"""
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for user_id_str, user_data in data.items():
                        user_id = int(user_id_str)
                        self.user_data[user_id] = UserData()
                        self.user_data[user_id].__dict__.update(user_data)
        except Exception as e:
            print(f"Ошибка загрузки данных: {e}")

    def save_data(self):
        """Сохраняет данные в файл"""
        try:
            data = {}
            for user_id, user_data in self.user_data.items():
                data[str(user_id)] = user_data.__dict__

            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения данных: {e}")

    def get_user_data(self, user_id: int) -> UserData:
        """Получает данные пользователя"""
        if user_id not in self.user_data:
            self.user_data[user_id] = UserData()
        return self.user_data[user_id]

    def add_coins(self, user_id: int, amount: int):
        """Добавляет монеты пользователю"""
        user_data = self.get_user_data(user_id)
        user_data.coins += amount
        self.save_data()

    def add_win(self, user_id: int):
        """Добавляет победу пользователю"""
        user_data = self.get_user_data(user_id)
        user_data.win_streak += 1
        user_data.max_win_streak = max(user_data.max_win_streak, user_data.win_streak)
        user_data.total_wins += 1
        user_data.coins += COINS_PER_WIN
        self.save_data()

    def add_loss(self, user_id: int):
        """Добавляет поражение пользователю"""
        user_data = self.get_user_data(user_id)
        user_data.win_streak = 0
        user_data.total_losses += 1
        self.save_data()

    def add_monster_kill(self, user_id: int, difficulty: str):
        """Добавляет убийство монстра пользователю"""
        user_data = self.get_user_data(user_id)
        if difficulty in user_data.monster_kills:
            user_data.monster_kills[difficulty] += 1
            self.save_data()

    def has_weapon(self, user_id: int, weapon_id: str) -> bool:
        """Проверяет, есть ли у пользователя оружие"""
        user_data = self.get_user_data(user_id)
        return weapon_id in user_data.weapons

    def buy_weapon(self, user_id: int, weapon_id: str, price: int):
        """Покупает оружие для пользователя"""
        user_data = self.get_user_data(user_id)
        user_data.coins -= price
        user_data.weapons.append(weapon_id)
        user_data.purchases[weapon_id] = datetime.now().isoformat()
        self.save_data()

    def set_current_weapon(self, user_id: int, weapon_id: str):
        """Устанавливает текущее оружие"""
        user_data = self.get_user_data(user_id)
        if weapon_id in user_data.weapons:
            user_data.current_weapon = weapon_id
            self.save_data()


data_store = DataStore()


# Состояния дуэлей и боев с монстрами
class DuelState:
    def __init__(self):
        self.duels: Dict[int, dict] = {}  # chat_id -> duel_info
        self.monster_battles: Dict[int, dict] = {}  # chat_id -> monster_battle_info
        self.user_mutes: Dict[int, datetime] = {}  # user_id -> mute_until
        self.mute_tasks: Dict[int, asyncio.Task] = {}  # user_id -> задача таймера
        self.mute_duration_minutes = 5  # стандартное время мута
        self.mute_enabled = True  # включен ли мут по умолчанию
        self.weapon_effects: Dict[str, dict] = {}  # Эффекты оружия для текущих дуэлей

    def set_mute_duration(self, minutes: int):
        self.mute_duration_minutes = minutes

    def toggle_mute(self, enabled: bool):
        self.mute_enabled = enabled

    def is_muted(self, user_id: int):
        """Проверяет, находится ли пользователь в муте"""
        if user_id in self.user_mutes:
            return self.user_mutes[user_id] > datetime.now()
        return False

    def get_weapon_effect(self, duel_id: int, user_id: int) -> dict:
        """Получает эффекты оружия для пользователя в дуэли"""
        key = f"{duel_id}_{user_id}"
        if key not in self.weapon_effects:
            self.weapon_effects[key] = {
                'deceive_used': False,
                'knockdown_used': False,
                'alert_used': False,
                'miss_streak': 0,
                'hit_count': 0,
                'skip_turn': False,
                'dodge_chance': 0,
                'ignore_second_life_chance': 0,
                'extra_lives_used': 0,
                'has_extra_life': False,
                'survive_hits_remaining': 0,
                'first_shot': True,
                'first_shot_done': False,
                'dodge_bonus': False
            }
        return self.weapon_effects[key]

    def clear_weapon_effects(self, duel_id: int):
        """Очищает эффекты оружия для дуэли"""
        keys_to_remove = [k for k in self.weapon_effects.keys() if k.startswith(f"{duel_id}_")]
        for key in keys_to_remove:
            del self.weapon_effects[key]

    def start_monster_battle(self, chat_id: int, user_id: int, monster: Monster):
        """Начинает бой с монстром"""
        self.monster_battles[chat_id] = {
            'user_id': user_id,
            'monster': monster,
            'state': 'active',
            'created_at': datetime.now(),
            'last_action': datetime.now(),
            'user_aim': 0,
            'user_air_shots': 3,
            'user_lives': 1,
            'user_accuracy_modifier': 1.0,
            'turn': 'user'  # Пользователь ходит первым
        }

    def end_monster_battle(self, chat_id: int):
        """Завершает бой с монстром"""
        if chat_id in self.monster_battles:
            del self.monster_battles[chat_id]


duel_state = DuelState()

# Оружия и их характеристики
WEAPONS = {
    "standard_musket": {
        "name": "Стандартный мушкет",
        "price": 0,
        "description": "Тот мушкет который есть у всех изначально",
        "category": "pistols",
        "melee": False
    },
    "flintlock_musket": {
        "name": "Мушкет кремневый",
        "price": 500,
        "description": "Стандартный шанс попадания но при прицеливании шанс попадания становится чуть чуть больше чем обычно",
        "category": "pistols",
        "melee": False,
        "aim_bonus": 1.1
    },
    "double_revolver": {
        "name": "Двухпульный револьвер",
        "price": 550,
        "description": "Делаешь два хода сразу, чуть чуть уменьшает шанс попадания, после своих двух выстрелов ты пропускаешь один ход, отсутствует способность выстрела в воздух",
        "category": "pistols",
        "melee": False,
        "double_turn": True,
        "accuracy_penalty": 0.9,
        "skip_after_double": True,
        "no_air_shot": True
    },
    "two_handed_musket": {
        "name": "Двуручный кремневый мушкет",
        "price": 600,
        "description": "Все выстрелы имеют шанс попадания в 1.5 раза больше, но после каждого выстрела ты пропускает ход, отсутствует способность выстрела в воздух",
        "category": "pistols",
        "melee": False,
        "damage_multiplier": 1.5,
        "skip_after_shot": True,
        "no_air_shot": True
    },
    "regular_bow": {
        "name": "Обычный лук",
        "price": 550,
        "description": "Каждый ход который вы промахиваетесь сразу же автоматически чуть чуть повышаете шанс на попадания, отсутствует способность выстрела в воздух, отсутствует способность прицеливания",
        "category": "bows",
        "melee": False,
        "miss_bonus": 1.05,
        "no_air_shot": True,
        "no_aim": True
    },
    "zoom_bow": {
        "name": "Зум/Приступ",
        "price": 600,
        "description": "При первом выстреле шанс попадания 25%, после хода соперника шанс попадания 50%, если после этого вы не убили соперника => вы автоматически умираете",
        "category": "bows",
        "melee": False,
        "first_shot_accuracy": 25,
        "second_shot_accuracy": 50,
        "suicide_if_no_kill": True,
        "no_air_shot": True
    },
    "heretic_bow": {
        "name": "Еретик",
        "price": 700,
        "description": "Сопернику в начале дается вторая жизнь бесплатно автоматически, при каждом попадании в соперника вы получаете вторую жизнь, отсутствует способность выстрела в воздух, шанс попадания чуть чуть ниже изначального",
        "category": "bows",
        "melee": False,
        "enemy_extra_life": True,
        "gain_life_on_hit": True,
        "accuracy_penalty": 0.9,
        "no_air_shot": True
    },
    "splinter_staff": {
        "name": "Заноза",
        "price": 700,
        "description": "Начинаешь играть с шансом попадания = 25%, с каждым ходом если вы не прицеливаетесь он будет уменьшатся на 5%, прицеливание слабее чем у остальных, отсутствует способность выстрела в воздух",
        "category": "staffs",
        "melee": False,
        "start_accuracy": 25,
        "accuracy_decay": 5,
        "weak_aim": True,
        "no_air_shot": True
    },
    "regular_staff": {
        "name": "Обычный посох",
        "price": 750,
        "description": "Как обычный мушкет, но имеет начальный шанс попадания 20%, отсутствует способность выстрела в воздух, прицеливание как у остальных",
        "category": "staffs",
        "melee": False,
        "start_accuracy": 20,
        "no_air_shot": True
    },
    "pure_staff": {
        "name": "Чистый посох",
        "price": 900,
        "description": "Как обычный мушкет, игнорирует дополнительные жизни убивая при попадании с одного удара, вместо 5 монет дает 10 монет, прицеливание как у остальных, отсутствует способность выстрела в воздух, начинаешь с шансом попадания 5%",
        "category": "staffs",
        "melee": False,
        "ignore_extra_lives": True,
        "coin_multiplier": 2,
        "start_accuracy": 5,
        "no_air_shot": True
    },
    "rapier": {
        "name": "Рапира",
        "price": 500,
        "description": "Вы делаете вместо одного два хода, всегда шанс попадания = 15%, отсутствует способность выстрела в воздух, шанс попадания чуть чуть ниже изначального, когда противник стреляет и все таки попадает с 15% шансом вы уворачиваетесь",
        "category": "melee",
        "melee": True,
        "double_turn": True,
        "fixed_accuracy": 15,
        "no_air_shot": True,
        "dodge_chance": 15,
        "base_dodge": 1
    },
    "halberd": {
        "name": "Алибарда",
        "price": 550,
        "description": "Всегда шанс попадания = 20%, когда противник стреляет и все таки попадает с 7% шансом вы уворачиваетесь",
        "category": "melee",
        "melee": True,
        "fixed_accuracy": 20,
        "dodge_chance": 7,
        "base_dodge": 1,
        "disrupt_chance": 5,
        "ignore_second_life_chance": 5
    },
    "hammer": {
        "name": "Молот",
        "price": 400,
        "description": "2 попадания гарантированно ты выживаешь, но у тебя всегда шанс попадания = 5%, когда противник стреляет и все таки попадает с 1% шансом вы уворачиваетесь",
        "category": "melee",
        "melee": True,
        "fixed_accuracy": 5,
        "survive_hits": 2,
        "dodge_chance": 1,
        "base_dodge": 1
    },
    "samsons_lock": {
        "name": "Самсонов локон",
        "price": 999999,
        "description": "3 попадания гарантированно ты выживаешь, после каждого попадания в вас у вас увеличивается автоматически шанс попадания 0=5% 1=15% 2=20% 3=50%, отсутствует способность выстрела в воздух, отсутствует способность прицеливания",
        "category": "special",
        "melee": True,
        "survive_hits": 3,
        "accuracy_per_hit": {0: 5, 1: 15, 2: 20, 3: 50},
        "no_air_shot": True,
        "no_aim": True,
        "base_dodge": 1
    },
    "golden_musket": {
        "name": "Золотой мушкет",
        "price": 999999,
        "description": "Стандартный мушкет, не имеет баффов, после убийства врага вы получаете вместо 5 монет => 50 монет",
        "category": "special",
        "melee": False,
        "coin_multiplier": 10
    }
}

# Приветственные сообщения
GREETINGS = [
    "⚔️ Приветствую, воины! Готовы к дуэлям?",
    "🔫 Добро пожаловать в мир дуэлей!",
    "🎩 Здравствуйте, господа дуэлянты!",
    "⚡ Бот для дуэлей к вашим услугам!",
    "🔥 Готовьтесь к честным поединкам!",
    "🎯 Привет! Давайте решим споры дуэлью!",
    "🛡️ Добро пожаловать в клуб дуэлянтов!",
    "💥 Бот-дуэлянт активирован!",
    "⚜️ Чести ради, жизни наперевес!",
    "🎖️ Готовы доказать свою правоту в бою?"
]

# Грустные сообщения при отказе
SAD_MESSAGES = [
    "😔 Дуэль отклонена... Как же печально.",
    "💔 Отказ принят. Сердце разбито.",
    "🌧️ Дуэль не состоялась. Даже небо плачет.",
    "🎻 Настроение испорчено. Музыка, грусти!",
    "📉 Энтузиазм упал ниже нуля.",
    "🥀 Роза завяла, дуэль отменена."
]

FUNNY_MESSAGES = [
    "🐔 Оппонент струсил! Кукареку!",
    "🏃‍♂️ Соперник сбежал быстрее ветра!",
    "🕊️ Мир во всем мире... или просто трусость?",
    "🍼 Видимо, пора менять подгузник!",
    "🎭 Драма! Трагедия! Отказ от дуэли!",
    "🧻 Бумажный воин не принял вызов!"
]

# Сообщения начала дуэли
DUEL_START_MESSAGES = [
    "⚔️ Дуэль началась! Да падут честно!",
    "🔫 Поединок начался! Пусть победит сильнейший!",
    "🎩 Господа, к барьеру! Начинаем!",
    "🔥 Огонь! Поединок стартовал!",
    "⚡ Дуэль запущена! Боги пулю направят!"
]

# Проценты попаданий для обычных пользователей
NORMAL_ACCURACY = {
    0: 1, 1: 5, 2: 9, 3: 10, 4: 25,
    5: 35, 6: 45, 7: 50, 8: 75, 9: 85, 10: 100
}

# Проценты попаданий для особого пользователя
SPECIAL_ACCURACY = {
    0: 10, 1: 25, 2: 50, 3: 75, 4: 90, 5: 100
}

# Сообщения для монстров
MONSTER_MESSAGES = {
    "spawn": [
        "👹 Из темноты появляется {name}! Приготовьтесь к битве!",
        "🐾 На вас напал {name}! Защищайтесь!",
        "👁️ {name} замечает вас и готовится к атаке!",
        "🌫️ Из тумана возникает {name}... Битва неизбежна!",
        "⚔️ {name} бросает вам вызов! Сражайтесь или бегите!"
    ],
    "treasure": [
        "💰 Вы нашли клад! Поздравляем!",
        "🎁 Неожиданная удача! Перед вами клад!",
        "💎 Блеск вдалеке оказывается сокровищем!",
        "🏆 Вы обнаружили спрятанные сокровища!"
    ],
    "attack": [
        "{name} атакует вас!",
        "{name} совершает выпад!",
        "{name} пытается нанести удар!",
        "Осторожно! {name} атакует!"
    ],
    "dodge": [
        "{name} уворачивается от вашей атаки!",
        "{name} ловко избегает удара!",
        "Ваша атака не достигает цели - {name} слишком быстр!",
        "{name} показывает мастерство уклонения!"
    ],
    "boost": [
        "{name} готовится к увороту!",
        "{name} сосредотачивается для уклонения!",
        "{name} увеличивает свою ловкость!",
        "{name} становится более уворотливым!"
    ]
}


def format_username(user):
    """Форматирует имя пользователя для отображения"""
    if user.username:
        return f"@{user.username}"
    elif user.first_name:
        return user.first_name
    else:
        return f"ID{user.id}"


def spawn_monster() -> Optional[Monster]:
    """Создает случайного монстра на основе вероятностей"""
    rand = random.random() * 100
    
    # Определяем тип монстра
    current_chance = 0
    for difficulty, config in MONSTER_DIFFICULTIES.items():
        current_chance += config["spawn_chance"]
        if rand <= current_chance:
            if difficulty == "treasure":
                # Для клада создаем особый объект
                monster = Monster("treasure")
                return monster
            else:
                monster = Monster(difficulty)
                return monster
    
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    greeting = random.choice(GREETINGS)

    # Получаем username бота из контекста
    bot_username = context.bot.username

    keyboard = [
        [
            InlineKeyboardButton("➕ Добавить в чат (с админкой)",
                                 url=f"https://t.me/{bot_username}?startgroup=true&admin=post_messages+delete_messages+restrict_members"),
            InlineKeyboardButton("⚙️ Настроить мут", callback_data="mute_settings")
        ],
        [
            InlineKeyboardButton("📖 Руководство", callback_data="guide"),
            InlineKeyboardButton("👤 Профиль", callback_data="profile")
        ],
        [
            InlineKeyboardButton("👹 Поиск монстра", callback_data="search_monster")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(greeting, reply_markup=reply_markup)


async def monster_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /monster"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Проверяем, не идет ли уже дуэль в чате
    if chat_id in duel_state.duels:
        await update.message.reply_text("⚠️ В этом чате уже идет дуэль! Подождите ее окончания.")
        return
    
    # Проверяем, не идет ли уже бой с монстром
    if chat_id in duel_state.monster_battles:
        await update.message.reply_text("⚠️ В этом чате уже идет бой с монстром!")
        return
    
    # Проверяем, находится ли пользователь в муте
    if duel_state.is_muted(user_id):
        remaining = (duel_state.user_mutes[user_id] - datetime.now()).seconds // 60
        await update.message.reply_text(f"⏰ Вы не можете искать монстров, так как у вас мут еще на {remaining} минут!")
        return

    # Создаем монстра
    monster = spawn_monster()
    
    if not monster:
        await update.message.reply_text("❌ Не удалось создать монстра. Попробуйте еще раз!")
        return

    # Начинаем бой с монстром
    duel_state.start_monster_battle(chat_id, user_id, monster)
    
    if monster.difficulty == "treasure":
        # Обработка клада
        coin_amount = random.randint(monster.config["coin_reward"][0], monster.config["coin_reward"][1])
        data_store.add_coins(user_id, coin_amount)
        data_store.add_monster_kill(user_id, "treasure")
        
        message = random.choice(MONSTER_MESSAGES["treasure"])
        await update.message.reply_text(
            f"{message}\n\n"
            f"💰 Вы получили: 🪙 {coin_amount} монет!\n"
            f"💎 Ваш баланс: 🪙 {data_store.get_user_data(user_id).coins} монет"
        )
        
        # Завершаем бой
        duel_state.end_monster_battle(chat_id)
        return
    
    # Для обычных монстров
    message = random.choice(MONSTER_MESSAGES["spawn"]).format(name=monster.name)
    
    difficulty_names = {
        "common": "Обычный",
        "rare": "Редкий",
        "mythic": "Мифический",
        "legendary": "Легендарный"
    }
    
    await update.message.reply_text(
        f"{message}\n\n"
        f"📊 Сложность: {difficulty_names[monster.difficulty]}\n"
        f"🎯 Шанс попадания монстра: {monster.accuracy}%\n"
        f"🔄 Шанс уворота монстра: {monster.dodge}%\n\n"
        f"⚔️ Бой начинается!"
    )
    
    # Показываем интерфейс боя
    await send_monster_battle_interface(chat_id, context.bot)


async def search_monster_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки поиска монстра"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    # Проверяем, не идет ли уже дуэль в чате
    if chat_id in duel_state.duels:
        await query.answer("⚠️ В этом чате уже идет дуэль!", show_alert=True)
        return
    
    # Проверяем, не идет ли уже бой с монстром
    if chat_id in duel_state.monster_battles:
        await query.answer("⚠️ В этом чате уже идет бой с монстром!", show_alert=True)
        return
    
    # Проверяем, находится ли пользователь в муте
    if duel_state.is_muted(user_id):
        remaining = (duel_state.user_mutes[user_id] - datetime.now()).seconds // 60
        await query.answer(f"⏰ Вы не можете искать монстров, так как у вас мут еще на {remaining} минут!", show_alert=True)
        return

    # Создаем монстра
    monster = spawn_monster()
    
    if not monster:
        await query.answer("❌ Не удалось создать монстра. Попробуйте еще раз!", show_alert=True)
        return

    # Начинаем бой с монстром
    duel_state.start_monster_battle(chat_id, user_id, monster)
    
    if monster.difficulty == "treasure":
        # Обработка клада
        coin_amount = random.randint(monster.config["coin_reward"][0], monster.config["coin_reward"][1])
        data_store.add_coins(user_id, coin_amount)
        data_store.add_monster_kill(user_id, "treasure")
        
        message = random.choice(MONSTER_MESSAGES["treasure"])
        await query.edit_message_text(
            f"{message}\n\n"
            f"💰 Вы получили: 🪙 {coin_amount} монет!\n"
            f"💎 Ваш баланс: 🪙 {data_store.get_user_data(user_id).coins} монет"
        )
        
        # Завершаем бой
        duel_state.end_monster_battle(chat_id)
        return
    
    # Для обычных монстров
    message = random.choice(MONSTER_MESSAGES["spawn"]).format(name=monster.name)
    
    difficulty_names = {
        "common": "Обычный",
        "rare": "Редкий",
        "mythic": "Мифический",
        "legendary": "Легендарный"
    }
    
    await query.edit_message_text(
        f"{message}\n\n"
        f"📊 Сложность: {difficulty_names[monster.difficulty]}\n"
        f"🎯 Шанс попадания монстра: {monster.accuracy}%\n"
        f"🔄 Шанс уворота монстра: {monster.dodge}%\n\n"
        f"⚔️ Бой начинается!"
    )
    
    # Показываем интерфейс боя
    await send_monster_battle_interface(chat_id, context.bot)


async def send_monster_battle_interface(chat_id: int, bot):
    """Отправляет интерфейс боя с монстром"""
    if chat_id not in duel_state.monster_battles:
        return
    
    battle_info = duel_state.monster_battles[chat_id]
    monster = battle_info['monster']
    user_id = battle_info['user_id']
    
    # Получаем информацию о пользователе
    user_data = data_store.get_user_data(user_id)
    current_weapon = WEAPONS.get(user_data.current_weapon, WEAPONS["standard_musket"])
    
    keyboard = []
    
    # Добавляем кнопки действий
    if current_weapon.get('melee'):
        # Кнопки для ближнего боя
        keyboard.append([InlineKeyboardButton("⚔️ Атака", callback_data=f"monster_action_{chat_id}_attack")])
        keyboard.append([InlineKeyboardButton("🎯 Прицелиться", callback_data=f"monster_action_{chat_id}_aim")])
    else:
        # Кнопки для дальнего боя
        if battle_info['user_air_shots'] > 0 and not current_weapon.get('no_air_shot'):
            keyboard.append([InlineKeyboardButton("🎈 Выстрел в воздух", callback_data=f"monster_action_{chat_id}_air")])
        
        if battle_info['user_aim'] < 10 and not current_weapon.get('no_aim'):
            keyboard.append([InlineKeyboardButton("🎯 Прицелиться (+1)", callback_data=f"monster_action_{chat_id}_aim")])
        
        keyboard.append([InlineKeyboardButton("🔫 Стрелять", callback_data=f"monster_action_{chat_id}_shoot")])
    
    keyboard.append([InlineKeyboardButton("🏃‍♂️ Сбежать", callback_data=f"monster_action_{chat_id}_flee")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_text = (
        f"👹 БОЙ С МОНСТРОМ\n\n"
        f"🎯 Монстр: {monster.name} ({monster.difficulty})\n"
        f"❤️ Жизней монстра: {monster.lives}\n"
        f"🎯 Шанс попадания монстра: {monster.accuracy}%\n"
        f"🔄 Шанс уворота монстра: {monster.dodge}%\n\n"
        f"👤 Ваша статистика:\n"
        f"❤️ Ваши жизни: {battle_info['user_lives']}\n"
        f"🎯 Ваш прицел: {battle_info['user_aim']}/10\n"
        f"🎈 Выстрелов в воздух: {battle_info['user_air_shots']}\n"
        f"🔫 Оружие: {current_weapon['name']}\n\n"
    )
    
    if monster.is_dodge_boosted:
        status_text += f"⚠️ Монстр готов к увороту!\n"
    if monster.is_accuracy_boosted:
        status_text += f"⚠️ Точность монстра повышена!\n"
    
    status_text += f"\n⏱️ У вас 5 минут на ход..."
    
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=status_text,
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Ошибка отправки интерфейса монстра: {e}")


async def handle_monster_action(query, context):
    """Обработчик действий в бою с монстром"""
    chat_id = int(query.data.split("_")[2])
    action = query.data.split("_")[3]
    
    if chat_id not in duel_state.monster_battles:
        await query.answer("⚠️ Бой уже завершен!", show_alert=True)
        return
    
    battle_info = duel_state.monster_battles[chat_id]
    monster = battle_info['monster']
    
    # Проверяем, что нажал тот же пользователь
    if query.from_user.id != battle_info['user_id']:
        await query.answer("❌ Это не ваш бой!", show_alert=True)
        return
    
    # Обновляем время последнего действия
    battle_info['last_action'] = datetime.now()
    
    user_data = data_store.get_user_data(battle_info['user_id'])
    current_weapon = WEAPONS.get(user_data.current_weapon, WEAPONS["standard_musket"])
    
    if action == "flee":
        # Пользователь сбегает
        duel_state.end_monster_battle(chat_id)
        await query.message.edit_text(
            f"🏃‍♂️ Вы сбежали от {monster.name}!\n"
            f"😔 Но это считается поражением..."
        )
        data_store.add_loss(battle_info['user_id'])
        return
    
    # Обработка действий пользователя
    if action == "air":
        # Выстрел в воздух
        if current_weapon.get('no_air_shot'):
            await query.answer("❌ Это оружие не может стрелять в воздух!", show_alert=True)
            return
        
        if battle_info['user_air_shots'] <= 0:
            await query.answer("❌ У вас не осталось выстрелов в воздух!", show_alert=True)
            return
        
        battle_info['user_air_shots'] -= 1
        battle_info['user_lives'] += 1
        battle_info['user_accuracy_modifier'] *= 0.9
        
        await query.message.edit_text(
            f"🎈 Вы сделали выстрел в воздух! +1 жизнь\n\n"
            f"Теперь ходит монстр..."
        )
        
        # Ход монстра
        await monster_turn(chat_id, context.bot, query.message)
        return
    
    elif action == "aim":
        # Прицеливание
        if current_weapon.get('no_aim'):
            await query.answer("❌ Это оружие не может прицеливаться!", show_alert=True)
            return
        
        if battle_info['user_aim'] < 10:
            battle_info['user_aim'] += 1
        
        await query.message.edit_text(
            f"🎯 Вы прицелились! Текущий прицел: {battle_info['user_aim']}/10\n\n"
            f"Теперь ходит монстр..."
        )
        
        # Ход монстра
        await monster_turn(chat_id, context.bot, query.message)
        return
    
    elif action == "shoot" or action == "attack":
        # Атака пользователя
        await handle_user_attack(chat_id, context.bot, query)
        return


async def handle_user_attack(chat_id: int, bot, query):
    """Обработка атаки пользователя на монстра"""
    battle_info = duel_state.monster_battles[chat_id]
    monster = battle_info['monster']
    user_id = battle_info['user_id']
    
    user_data = data_store.get_user_data(user_id)
    current_weapon = WEAPONS.get(user_data.current_weapon, WEAPONS["standard_musket"])
    
    # Определяем точность пользователя
    if current_weapon.get('fixed_accuracy'):
        accuracy = current_weapon['fixed_accuracy']
    elif query.from_user.username and query.from_user.username.lower() == "bi1ro":
        accuracy_table = SPECIAL_ACCURACY
        user_aim = battle_info['user_aim']
        accuracy = accuracy_table.get(min(user_aim, 5), 100)
    else:
        accuracy_table = NORMAL_ACCURACY
        user_aim = battle_info['user_aim']
        accuracy = accuracy_table.get(min(user_aim, 10), 100)
    
    # Применяем модификатор
    accuracy_modifier = battle_info['user_accuracy_modifier']
    final_accuracy = accuracy * accuracy_modifier
    
    # Проверяем уворот монстра
    dodge_chance = monster.dodge
    if monster.is_dodge_boosted:
        dodge_chance = monster.config["max_dodge"]
    
    dodged = random.randint(1, 100) <= dodge_chance
    
    if dodged:
        # Монстр уворачивается
        message = random.choice(MONSTER_MESSAGES["dodge"]).format(name=monster.name)
        await query.message.edit_text(
            f"{message}\n\n"
            f"Теперь ходит монстр..."
        )
        
        # Сбрасываем усиленный уворот
        if monster.is_dodge_boosted:
            monster.is_dodge_boosted = False
            monster.dodge = monster.config["base_dodge"]
        
        # Ход монстра
        await monster_turn(chat_id, bot, query.message)
        return
    
    # Проверяем попадание
    hit = random.randint(1, 100) <= final_accuracy
    
    if not hit:
        # Промах
        await query.message.edit_text(
            f"🌬️ Вы промахнулись по {monster.name}!\n\n"
            f"Теперь ходит монстр..."
        )
        
        # Эффекты при промахе
        if current_weapon.get('miss_bonus'):
            battle_info['user_accuracy_modifier'] *= current_weapon['miss_bonus']
        
        # Ход монстра
        await monster_turn(chat_id, bot, query.message)
        return
    
    # ПОПАДАНИЕ
    # Проверяем игнорирование дополнительных жизней
    ignore_extra_lives = current_weapon.get('ignore_extra_lives', False)
    
    # Наносим урон монстру
    monster.lives -= 1
    
    result_text = f"💥 Вы попали в {monster.name}!"
    
    # Для некоторых оружий - эффекты при попадании
    if current_weapon.get('gain_life_on_hit'):
        battle_info['user_lives'] += 1
        result_text += f"\n➕ Вы получаете дополнительную жизнь!"
    
    # Сбрасываем прицел после выстрела
    battle_info['user_aim'] = 0
    
    await query.message.edit_text(result_text)
    
    # Проверяем, не убит ли монстр
    if monster.lives <= 0:
        await end_monster_battle(chat_id, bot, user_id, monster, True)
    else:
        # Ход монстра
        await monster_turn(chat_id, bot, query.message)


async def monster_turn(chat_id: int, bot, message):
    """Ход монстра"""
    if chat_id not in duel_state.monster_battles:
        return
    
    battle_info = duel_state.monster_battles[chat_id]
    monster = battle_info['monster']
    user_id = battle_info['user_id']
    
    # Монстр может повысить точность
    if not monster.is_accuracy_boosted:
        if random.randint(1, 100) <= monster.config.get("accuracy_boost_chance", 0):
            monster.accuracy = min(monster.accuracy + 5, monster.config["max_accuracy"])
            monster.is_accuracy_boosted = True
    
    # Монстр может подготовиться к увороту
    if not monster.is_dodge_boosted:
        if random.randint(1, 100) <= monster.config.get("dodge_boost_chance", 0):
            monster.is_dodge_boosted = True
    
    # Монстр атакует
    if random.randint(1, 100) <= monster.config.get("attack_chance", 50):
        attack_message = random.choice(MONSTER_MESSAGES["attack"]).format(name=monster.name)
        
        # Определяем шанс попадания монстра
        monster_accuracy = monster.accuracy
        if monster.is_accuracy_boosted:
            monster_accuracy = monster.config["max_accuracy"]
        
        # Проверяем попадание
        hit = random.randint(1, 100) <= monster_accuracy
        
        if hit:
            # Особые способности монстров
            if monster.difficulty == "rare" and random.randint(1, 100) <= monster.config.get("steal_life_chance", 0):
                # Крадет жизнь у игрока
                if battle_info['user_lives'] > 1:
                    battle_info['user_lives'] -= 1
                    monster.has_extra_life = True
                    attack_message += f"\n😱 {monster.name} крадет у вас жизнь!"
                else:
                    battle_info['user_lives'] -= 1
                    attack_message += f"\n💥 {monster.name} попадает в вас!"
            elif monster.difficulty == "mythic" and random.randint(1, 100) <= monster.config.get("knockdown_chance", 0):
                # Валяет врага и добавляет себе жизнь
                battle_info['user_lives'] -= 1
                monster.lives += 1
                attack_message += f"\n🤕 {monster.name} валит вас с ног и добавляет себе жизнь!"
            elif monster.difficulty == "legendary" and random.randint(1, 100) <= monster.config.get("steal_life_chance", 0):
                # Сбивает прицел, валит с ног и крадет жизнь
                battle_info['user_aim'] = 0
                battle_info['user_lives'] -= 1
                
                if battle_info['user_lives'] > 0:
                    monster.has_extra_life = True
                    battle_info['user_lives'] -= 1
                    attack_message += f"\n😈 {monster.name} сбивает ваш прицел, валит с ног и крадет жизнь!"
                else:
                    monster.lives += 1
                    attack_message += f"\n😈 {monster.name} сбивает ваш прицел, валит с ног и добавляет себе жизнь!"
            else:
                # Обычная атака
                battle_info['user_lives'] -= 1
                attack_message += f"\n💥 {monster.name} попадает в вас!"
        else:
            attack_message += f"\n🌬️ {monster.name} промахивается!"
    else:
        attack_message = f"{monster.name} не атакует в этот ход."
    
    # Сбрасываем усиления после хода
    if monster.is_dodge_boosted:
        monster.is_dodge_boosted = False
        monster.dodge = monster.config["base_dodge"]
    
    if monster.is_accuracy_boosted:
        monster.is_accuracy_boosted = False
        monster.accuracy = monster.config["base_accuracy"]
    
    await message.edit_text(f"{attack_message}\n\nВаш ход...")
    
    # Проверяем, не погиб ли игрок
    if battle_info['user_lives'] <= 0:
        await end_monster_battle(chat_id, bot, user_id, monster, False)
    else:
        # Обновляем интерфейс для хода пользователя
        await send_monster_battle_interface(chat_id, bot)


async def end_monster_battle(chat_id: int, bot, user_id: int, monster: Monster, user_won: bool):
    """Завершает бой с монстром"""
    if chat_id not in duel_state.monster_battles:
        return
    
    duel_state.end_monster_battle(chat_id)
    
    if user_won:
        # Пользователь победил
        coin_reward = random.randint(monster.config["coin_reward"][0], monster.config["coin_reward"][1])
        data_store.add_coins(user_id, coin_reward)
        data_store.add_monster_kill(user_id, monster.difficulty)
        data_store.add_win(user_id)
        
        difficulty_names = {
            "common": "обычного",
            "rare": "редкого",
            "mythic": "мифического",
            "legendary": "легендарного"
        }
        
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"🏆 ПОБЕДА!\n\n"
                f"Вы победили {monster.name} ({difficulty_names[monster.difficulty]} монстра)!\n"
                f"💰 Награда: 🪙 {coin_reward} монет\n"
                f"💎 Ваш баланс: 🪙 {data_store.get_user_data(user_id).coins} монет\n\n"
                f"🎯 Убийств {difficulty_names[monster.difficulty]}: {data_store.get_user_data(user_id).monster_kills[monster.difficulty]}"
            )
        )
    else:
        # Пользователь проиграл
        data_store.add_loss(user_id)
        
        if duel_state.mute_enabled:
            mute_duration = duel_state.mute_duration_minutes
            user_name = format_username(await bot.get_chat(user_id))
            
            # Применяем мут
            duel_state.user_mutes[user_id] = datetime.now() + timedelta(minutes=mute_duration)
            
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"💀 ПОРАЖЕНИЕ!\n\n"
                    f"{monster.name} победил вас!\n"
                    f"⏰ Вы получаете мут на {mute_duration} минут за поражение!"
                )
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"💀 ПОРАЖЕНИЕ!\n\n"
                    f"{monster.name} победил вас!\n"
                    f"🟢 Система мута отключена - вы не получили мут."
                )
            )


async def profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки профиля"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_data = data_store.get_user_data(user_id)

    # Получаем текущее оружие
    current_weapon = WEAPONS.get(user_data.current_weapon, WEAPONS["standard_musket"])

    profile_text = (
        f"👤 **ДУЭЛЬНЫЙ ПРОФИЛЬ**\n\n"
        f"Игрок: {format_username(query.from_user)}\n"
        f"Серия побед: {user_data.win_streak}\n"
        f"Макс. серия побед: {user_data.max_win_streak}\n"
        f"Всего побед: {user_data.total_wins}\n"
        f"Всего поражений: {user_data.total_losses}\n"
        f"Монет: 🪙 {user_data.coins}\n\n"
        f"🎯 Текущее оружие: {current_weapon['name']}\n"
        f"📦 Оружий в коллекции: {len(user_data.weapons)}\n\n"
        f"👹 **СТАТИСТИКА МОНСТРОВ**\n"
        f"• Обычных убито: {user_data.monster_kills['common']}\n"
        f"• Редких убито: {user_data.monster_kills['rare']}\n"
        f"• Мифических убито: {user_data.monster_kills['mythic']}\n"
        f"• Легендарных убито: {user_data.monster_kills['legendary']}\n"
        f"• Кладов найдено: {user_data.monster_kills['treasure']}"
    )

    keyboard = [
        [InlineKeyboardButton("🛒 Магазин", callback_data="shop_main")],
        [InlineKeyboardButton("👹 Поиск монстра", callback_data="search_monster")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(profile_text, reply_markup=reply_markup, parse_mode='Markdown')


async def shop_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню магазина"""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🔫 Пистолеты", callback_data="shop_pistols_1")],
        [InlineKeyboardButton("🏹 Луки", callback_data="shop_bows_1")],
        [InlineKeyboardButton("🧙‍♂️ Посохи", callback_data="shop_staffs_1")],
        [InlineKeyboardButton("⚔️ Ближнее оружие", callback_data="shop_melee_1")],
        [InlineKeyboardButton("🌟 Особое", callback_data="shop_special_1")],
        [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🛒 **МАГАЗИН ОРУЖИЯ**\n\n"
        "Выберите категорию оружия:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def shop_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает оружие в категории"""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("_")

    if len(parts) < 3:
        await query.edit_message_text("⚠️ Ошибка в данных магазина!")
        return

    category = parts[1]
    page = int(parts[2])

    # Фильтруем оружие по категории
    category_weapons = []
    for weapon_id, weapon_info in WEAPONS.items():
        if weapon_info["category"] == category:
            category_weapons.append((weapon_id, weapon_info))

    # Сортируем по цене
    category_weapons.sort(key=lambda x: x[1]["price"])

    # Разбиваем на страницы (по 3 оружия на страницу)
    weapons_per_page = 3
    start_idx = (page - 1) * weapons_per_page
    end_idx = start_idx + weapons_per_page
    page_weapons = category_weapons[start_idx:end_idx]

    # Создаем текст страницы
    category_names = {
        "pistols": "🔫 Пистолеты",
        "bows": "🏹 Луки",
        "staffs": "🧙‍♂️ Посохи",
        "melee": "⚔️ Ближнее оружие",
        "special": "🌟 Особое"
    }

    text = f"{category_names[category]} - Страница {page}\n\n"

    for i, (weapon_id, weapon_info) in enumerate(page_weapons, 1):
        user_data = data_store.get_user_data(query.from_user.id)
        has_weapon = weapon_id in user_data.weapons
        is_current = user_data.current_weapon == weapon_id

        # Проверяем, может ли пользователь купить оружие
        can_buy = (user_data.coins >= weapon_info["price"] or
                   (query.from_user.username and query.from_user.username.lower() == "bi1ro"))

        status = "✅ (Ваше)" if is_current else "🛒 (Куплено)" if has_weapon else "💰 (Доступно)" if can_buy else "🔒 (Недоступно)"

        text += f"{i}. {weapon_info['name']} - 🪙 {weapon_info['price']}\n"
        text += f"   {weapon_info['description']}\n"
        text += f"   {status}\n\n"

    # Создаем клавиатуру
    keyboard = []

    # Кнопки для оружия
    for i, (weapon_id, _) in enumerate(page_weapons, 1):
        callback_data = f"view_weapon_{weapon_id}"
        keyboard.append([InlineKeyboardButton(f"{i}. Выбрать/Купить", callback_data=callback_data)])

    # Кнопки навигации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"shop_{category}_{page - 1}"))
    if end_idx < len(category_weapons):
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"shop_{category}_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 Назад в магазин", callback_data="shop_main")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup)


async def view_weapon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр деталей оружия"""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("_")

    if len(parts) < 3:
        await query.edit_message_text("⚠️ Ошибка в данных оружия!")
        return

    weapon_id = "_".join(parts[2:])  # Объединяем все части после "view_weapon_"
    weapon_info = WEAPONS.get(weapon_id)

    if not weapon_info:
        await query.edit_message_text(f"⚠️ Оружие не найдено! ID: {weapon_id}")
        return

    user_id = query.from_user.id
    user_data = data_store.get_user_data(user_id)

    has_weapon = weapon_id in user_data.weapons
    is_current = user_data.current_weapon == weapon_id
    can_buy = (user_data.coins >= weapon_info["price"] or
               (query.from_user.username and query.from_user.username.lower() == "bi1ro"))

    text = f"🎯 **{weapon_info['name']}**\n\n"
    text += f"📝 Описание: {weapon_info['description']}\n"
    text += f"💰 Цена: 🪙 {weapon_info['price']}\n"
    text += f"📦 Категория: {weapon_info['category']}\n\n"
    text += f"💎 Ваш баланс: 🪙 {user_data.coins}\n\n"

    if has_weapon:
        if is_current:
            text += "✅ Это оружие сейчас активно!"
        else:
            text += "✅ Это оружие у вас есть!"
    elif can_buy:
        text += "🛒 Вы можете купить это оружие!"
    else:
        text += "❌ Недостаточно монет для покупки!"

    keyboard = []

    if has_weapon and not is_current:
        keyboard.append([InlineKeyboardButton("🎯 Выбрать это оружие", callback_data=f"equip_{weapon_id}")])
    elif not has_weapon and can_buy:
        keyboard.append([InlineKeyboardButton("💰 Купить", callback_data=f"buy_{weapon_id}")])

    # Кнопка назад - возвращаемся к соответствующей категории
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"shop_{weapon_info['category']}_1")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def equip_weapon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор оружия"""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("_")

    if len(parts) < 2:
        await query.edit_message_text("⚠️ Ошибка в данных оружия!")
        return

    weapon_id = "_".join(parts[1:])  # Объединяем все части после "equip_"

    data_store.set_current_weapon(query.from_user.id, weapon_id)

    weapon_info = WEAPONS.get(weapon_id, WEAPONS["standard_musket"])

    await query.edit_message_text(
        f"✅ Оружие '{weapon_info['name']}' теперь активно!\n"
        f"Оно будет использоваться в следующих дуэлях.",
        parse_mode='Markdown'
    )


async def buy_weapon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка оружия"""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("_")

    if len(parts) < 2:
        await query.edit_message_text("⚠️ Ошибка в данных оружия!")
        return

    weapon_id = "_".join(parts[1:])  # Объединяем все части после "buy_"
    weapon_info = WEAPONS.get(weapon_id)

    if not weapon_info:
        await query.edit_message_text(f"⚠️ Оружие не найдено! ID: {weapon_id}")
        return

    user_id = query.from_user.id
    user_data = data_store.get_user_data(user_id)

    # Проверяем, есть ли уже это оружие
    if weapon_id in user_data.weapons:
        await query.edit_message_text("⚠️ У вас уже есть это оружие!")
        return

    # Проверяем, может ли пользователь купить
    can_buy_for_free = (query.from_user.username and query.from_user.username.lower() == "bi1ro")

    if not can_buy_for_free and user_data.coins < weapon_info["price"]:
        await query.edit_message_text("❌ Недостаточно монет для покупки!")
        return

    # Подтверждение покупки
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, купить", callback_data=f"confirm_buy_{weapon_id}"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data=f"view_weapon_{weapon_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"❓ Вы уверены, что хотите купить '{weapon_info['name']}' за 🪙 {weapon_info['price']}?",
        reply_markup=reply_markup
    )


async def confirm_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение покупки"""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("_")

    if len(parts) < 3:
        await query.edit_message_text("⚠️ Ошибка в данных покупки!")
        return

    weapon_id = "_".join(parts[2:])  # Объединяем все части после "confirm_buy_"
    weapon_info = WEAPONS.get(weapon_id)

    if not weapon_info:
        await query.edit_message_text(f"⚠️ Оружие не найдено! ID: {weapon_id}")
        return

    user_id = query.from_user.id
    user_data = data_store.get_user_data(user_id)

    # Проверяем, может ли пользователь купить
    can_buy_for_free = (query.from_user.username and query.from_user.username.lower() == "bi1ro")

    if not can_buy_for_free:
        if user_data.coins < weapon_info["price"]:
            await query.edit_message_text("❌ Недостаточно монет для покупки!")
            return

        # Списание монет
        data_store.buy_weapon(user_id, weapon_id, weapon_info["price"])
    else:
        # Бесплатная покупка для @Bi1ro
        data_store.buy_weapon(user_id, weapon_id, 0)

    # Автоматически выбираем купленное оружие
    data_store.set_current_weapon(user_id, weapon_id)

    await query.edit_message_text(
        f"🎉 Поздравляем! Вы купили '{weapon_info['name']}'!\n"
        f"✅ Оружие автоматически выбрано для использования.",
        parse_mode='Markdown'
    )


async def mute_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки настроек мута"""
    query = update.callback_query
    await query.answer()

    # Проверяем, является ли пользователь создателем чата
    try:
        chat_member = await context.bot.get_chat_member(query.message.chat_id, query.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await query.answer("❌ Только администраторы чата могут настраивать мут!", show_alert=True)
            return
    except:
        await query.answer("❌ Ошибка проверки прав доступа!", show_alert=True)
        return

    mute_status = "✅ ВКЛЮЧЕН" if duel_state.mute_enabled else "❌ ОТКЛЮЧЕН"

    keyboard = [
        [
            InlineKeyboardButton("⏱️ Установить время мута", callback_data="configure_mute")
        ],
        [
            InlineKeyboardButton("✅ Мут ВКЛЮЧИТЬ", callback_data="enable_mute"),
            InlineKeyboardButton("❌ Мут ОТКЛЮЧИТЬ", callback_data="disable_mute")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"⚙️ **НАСТРОЙКИ МУТА**\n\n"
        f"Текущий статус: {mute_status}\n"
        f"Длительность мута: {duel_state.mute_duration_minutes} минут\n\n"
        f"• Установите время мута для проигравших\n"
        f"• Включите/отключите систему мута\n"
        f"• При отключении проигравшие не будут получать мут",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def enable_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Включение мута"""
    query = update.callback_query
    await query.answer()

    # Проверяем, является ли пользователь создателем чата
    try:
        chat_member = await context.bot.get_chat_member(query.message.chat_id, query.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await query.answer("❌ Только администраторы чата могут настраивать мут!", show_alert=True)
            return
    except:
        await query.answer("❌ Ошибка проверки прав доступа!", show_alert=True)
        return

    duel_state.toggle_mute(True)
    await query.edit_message_text(
        f"✅ Система мута ВКЛЮЧЕНА\n"
        f"Проигравшие будут получать мут на {duel_state.mute_duration_minutes} минут"
    )


async def disable_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отключение мута"""
    query = update.callback_query
    await query.answer()

    # Проверяем, является ли пользователь создателем чата
    try:
        chat_member = await context.bot.get_chat_member(query.message.chat_id, query.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await query.answer("❌ Только администраторы чата могут настраивать мут!", show_alert=True)
            return
    except:
        await query.answer("❌ Ошибка проверки прав доступа!", show_alert=True)
        return

    duel_state.toggle_mute(False)
    await query.edit_message_text(
        f"❌ Система мута ОТКЛЮЧЕНА\n"
        f"Проигравшие НЕ будут получать мут"
    )


async def guide_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки руководства"""
    query = update.callback_query
    await query.answer()

    guide_text = """
📖 **РУКОВОДСТВО ПО ДУЭЛЯМ**

⚔️ **Как вызвать на дуэль:**
1. Найти сообщение человека, с которым хотите дуэлиться
2. Ответить на его сообщение командой: `!дуэль`
3. Ожидать, пока человек примет вызов

🎮 **Кнопки в дуэли:**
• 🎈 **Выстрел в воздух** - дает дополнительную жизнь (можно использовать 3 раза)
• 🎯 **Прицелиться** - повышает точность выстрела
• 🔫 **Стрелять** - выстрел с текущей точностью
• 🌀 **Сбить прицел** - обнуляет точность соперника
• ✖️ **Отменить дуэль** - досрочное завершение дуэли

⚙️ **Система точности:**
- Прицел увеличивает шанс попадания
- Максимальный прицел: 10

⏱️ **Таймауты:**
- 5 минут на принятие дуэли
- 5 минут на ход в дуэли
- Проигравший получает мут на 5 минут (настраивается)

🎯 **Правила:**
- Только участники дуэли могут нажимать кнопки
- Ходы делаются по очереди
- Дуэль заканчивается при потере всех жизней

👹 **БОЙ С МОНСТРАМИ:**
• Используйте команду `/monster` или кнопку "Поиск монстра"
• 5 типов встреч: Обычный, Редкий, Мифический, Легендарный, Клад
• Каждый монстр имеет уникальные характеристики
• Победа над монстром дает награду в монетах
• Поражение от монстра дает мут (если включен)

💡 **Совет:** Используйте выстрелы в воздух для дополнительных жизней, но помните, что точность снижается после каждого!
    """

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(guide_text, reply_markup=reply_markup, parse_mode='Markdown')


async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()

    greeting = random.choice(GREETINGS)

    # Получаем username бота из контекста
    bot_username = context.bot.username

    keyboard = [
        [
            InlineKeyboardButton("➕ Добавить в чат (с админкой)",
                                 url=f"https://t.me/{bot_username}?startgroup=true&admin=post_messages+delete_messages+restrict_members"),
            InlineKeyboardButton("⚙️ Настроить мут", callback_data="mute_settings")
        ],
        [
            InlineKeyboardButton("📖 Руководство", callback_data="guide"),
            InlineKeyboardButton("👤 Профиль", callback_data="profile")
        ],
        [
            InlineKeyboardButton("👹 Поиск монстра", callback_data="search_monster")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(greeting, reply_markup=reply_markup)


async def configure_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки настройки времени мута"""
    query = update.callback_query
    await query.answer()

    # Проверяем, является ли пользователь создателем чата
    try:
        chat_member = await context.bot.get_chat_member(query.message.chat_id, query.from_user.id)
        if chat_member.status not in ["creator", "administrator"]:
            await query.answer("❌ Только администраторы чата могут настраивать мут!", show_alert=True)
            return
    except:
        await query.answer("❌ Ошибка проверки прав доступа!", show_alert=True)
        return

    await query.edit_message_text(
        "⏱️ Введите количество минут для мута (только цифру):"
    )

    # Сохраняем состояние ожидания ввода
    context.user_data['awaiting_mute_input'] = True


async def handle_mute_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода времени мута"""
    if not context.user_data.get('awaiting_mute_input'):
        return

    try:
        minutes = int(update.message.text.strip())
        if minutes <= 0:
            await update.message.reply_text("⚠️ Введите положительное число!")
            return

        context.user_data['proposed_mute'] = minutes

        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data=f"confirm_mute_{minutes}"),
                InlineKeyboardButton("❌ Нет", callback_data="cancel_mute")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"❓ Вы уверены, что хотите установить мут на {minutes} минут?",
            reply_markup=reply_markup
        )

    except ValueError:
        await update.message.reply_text("⚠️ Пожалуйста, введите только цифру!")


async def handle_mute_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик подтверждения мута"""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("confirm_mute_"):
        minutes = int(query.data.split("_")[2])
        duel_state.set_mute_duration(minutes)

        await query.edit_message_text(
            f"✅ Время мута установлено на {minutes} минут!"
        )
    else:
        await query.edit_message_text(
            "❌ Настройка мута отменена."
        )

    context.user_data.pop('awaiting_mute_input', None)
    context.user_data.pop('proposed_mute', None)


async def handle_duel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды !дуэль в ответ на сообщение"""
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ Чтобы вызвать на дуэль, ответьте командой `!дуэль` на сообщение соперника.\n\n"
            "📖 Используйте /start и нажмите 'Руководство' для подробной инструкции."
        )
        return

    caller = update.message.from_user
    target = update.message.reply_to_message.from_user

    if caller.id == target.id:
        await update.message.reply_text("🤨 Нельзя вызвать на дуэль самого себя!")
        return

    chat_id = update.message.chat_id

    # Проверяем, не идет ли уже дуэль в этом чате
    if chat_id in duel_state.duels:
        await update.message.reply_text("⚠️ В этом чате уже идет дуэль!")
        return
    
    # Проверяем, не идет ли уже бой с монстром в этом чате
    if chat_id in duel_state.monster_battles:
        await update.message.reply_text("⚠️ В этом чате уже идет бой с монстром!")
        return

    # Проверяем, не находится ли кто-то в муте
    if duel_state.is_muted(caller.id):
        remaining = (duel_state.user_mutes[caller.id] - datetime.now()).seconds // 60
        await update.message.reply_text(f"⏰ Вы не можете вызвать на дуэль, так как у вас мут еще на {remaining} минут!")
        return

    if duel_state.is_muted(target.id):
        remaining = (duel_state.user_mutes[target.id] - datetime.now()).seconds // 60
        await update.message.reply_text(f"⏰ Этот пользователь в муте еще на {remaining} минут!")
        return

    # Получаем оружие игроков
    caller_weapon = data_store.get_user_data(caller.id).current_weapon
    target_weapon = data_store.get_user_data(target.id).current_weapon

    caller_weapon_info = WEAPONS.get(caller_weapon, WEAPONS["standard_musket"])
    target_weapon_info = WEAPONS.get(target_weapon, WEAPONS["standard_musket"])

    # Создаем запрос на дуэль
    duel_state.duels[chat_id] = {
        'caller': caller,
        'target': target,
        'caller_weapon': caller_weapon,
        'target_weapon': target_weapon,
        'state': 'waiting',
        'created_at': datetime.now(),
        'turn': None,
        'caller_aim': 0,
        'target_aim': 0,
        'caller_air_shots': 3,
        'target_air_shots': 3,
        'caller_lives': 1,
        'target_lives': 1,
        'caller_accuracy_modifier': 1.0,
        'target_accuracy_modifier': 1.0,
        'last_action': datetime.now(),
        'caller_effects': {},
        'target_effects': {},
        'caller_weapon_info': caller_weapon_info,
        'target_weapon_info': target_weapon_info,
        'caller_skip_turn': False,
        'target_skip_turn': False
    }

    # Применяем начальные эффекты оружий
    await apply_weapon_start_effects(chat_id)

    keyboard = [
        [
            InlineKeyboardButton("✅ Принять дуэль", callback_data=f"accept_duel_{chat_id}"),
            InlineKeyboardButton("❌ Отклонить дуэль", callback_data=f"reject_duel_{chat_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Используем форматированные имена
    caller_name = format_username(caller)
    target_name = format_username(target)

    message = await update.message.reply_text(
        f"⚔️ ВНИМАНИЕ {target_name}!\n"
        f"Вас вызывает на дуэль {caller_name}!\n\n"
        f"Оружие вызывающего: {caller_weapon_info['name']}\n"
        f"Оружие вызванного: {target_weapon_info['name']}\n\n"
        f"Примете ли вы вызов?\n"
        f"⏱️ У вас 5 минут на ответ",
        reply_markup=reply_markup
    )

    duel_state.duels[chat_id]['message_id'] = message.message_id

    # Запускаем таймер ожидания
    asyncio.create_task(duel_timeout(chat_id, context.bot))


async def apply_weapon_start_effects(chat_id: int):
    """Применяет начальные эффекты оружий"""
    if chat_id not in duel_state.duels:
        return

    duel_info = duel_state.duels[chat_id]
    caller_weapon = duel_info['caller_weapon_info']
    target_weapon = duel_info['target_weapon_info']

    # Инициализируем эффекты оружия
    caller_effects = duel_state.get_weapon_effect(chat_id, duel_info['caller'].id)
    target_effects = duel_state.get_weapon_effect(chat_id, duel_info['target'].id)

    # Эффекты для вызывающего
    if caller_weapon.get('enemy_extra_life'):
        # Даем вторую жизнь сопернику
        duel_info['target_lives'] += 1
        target_effects['has_extra_life'] = True

    if caller_weapon.get('survive_hits'):
        caller_effects['survive_hits_remaining'] = caller_weapon['survive_hits']

    if caller_weapon.get('start_accuracy'):
        # Устанавливаем начальную точность
        pass

    # Эффекты для вызываемого
    if target_weapon.get('enemy_extra_life'):
        # Даем вторую жизнь сопернику
        duel_info['caller_lives'] += 1
        caller_effects['has_extra_life'] = True

    if target_weapon.get('survive_hits'):
        target_effects['survive_hits_remaining'] = target_weapon['survive_hits']

    if target_weapon.get('start_accuracy'):
        # Устанавливаем начальную точность
        pass


async def duel_timeout(chat_id: int, bot):
    """Таймаут ожидания принятия дуэли"""
    await asyncio.sleep(300)  # 5 минут

    if chat_id in duel_state.duels and duel_state.duels[chat_id]['state'] == 'waiting':
        duel_info = duel_state.duels.pop(chat_id)

        message = random.choice(SAD_MESSAGES + FUNNY_MESSAGES)
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=duel_info['message_id'],
                text=f"⏰ Время вышло! Дуэль отменена.\n{message}"
            )
        except:
            pass


async def duel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок дуэли"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "guide":
        await guide_callback(update, context)
    elif data == "profile":
        await profile_callback(update, context)
    elif data == "back_to_main":
        await back_to_main_callback(update, context)
    elif data == "mute_settings":
        await mute_settings_callback(update, context)
    elif data == "enable_mute":
        await enable_mute_callback(update, context)
    elif data == "disable_mute":
        await disable_mute_callback(update, context)
    elif data.startswith("accept_duel_"):
        await handle_duel_accept(query, context)
    elif data.startswith("reject_duel_"):
        await handle_duel_reject(query, context)
    elif data.startswith("duel_action_"):
        await handle_duel_action(query, context)
    elif data.startswith("confirm_mute_") or data == "cancel_mute":
        await handle_mute_confirmation(update, context)
    elif data == "shop_main":
        await shop_main_callback(update, context)
    elif data.startswith("shop_"):
        await shop_category_callback(update, context)
    elif data.startswith("view_weapon_"):
        await view_weapon_callback(update, context)
    elif data.startswith("equip_"):
        await equip_weapon_callback(update, context)
    elif data.startswith("buy_"):
        await buy_weapon_callback(update, context)
    elif data.startswith("confirm_buy_"):
        await confirm_buy_callback(update, context)
    elif data == "search_monster":
        await search_monster_callback(update, context)
    elif data.startswith("monster_action_"):
        await handle_monster_action(query, context)


async def handle_duel_accept(query, context):
    """Обработчик принятия дуэли"""
    chat_id = int(query.data.split("_")[2])

    if chat_id not in duel_state.duels:
        await query.edit_message_text("⚠️ Дуэль уже неактуальна.")
        return

    duel_info = duel_state.duels[chat_id]

    # Проверяем, что нажал именно тот, кому был вызов
    if query.from_user.id != duel_info['target'].id:
        await query.answer("❌ Только вызванный участник может принимать дуэль!", show_alert=True)
        return

    duel_info['state'] = 'active'
    duel_info['turn'] = 'caller'  # Первым ходит вызвавший
    duel_info['started_at'] = datetime.now()
    duel_info['last_action'] = datetime.now()

    start_message = random.choice(DUEL_START_MESSAGES)

    # Используем форматированные имена
    caller_name = format_username(duel_info['caller'])
    target_name = format_username(duel_info['target'])

    await query.edit_message_text(
        f"{start_message}\n\n"
        f"🎯 Участники:\n"
        f"• {caller_name} ({duel_info['caller_weapon_info']['name']})\n"
        f"• {target_name} ({duel_info['target_weapon_info']['name']})\n\n"
        f"📯 Первым ходит: {caller_name}\n\n"
        f"⚡ Дуэль началась!"
    )

    # Показываем интерфейс дуэли
    await send_duel_interface(chat_id, context.bot)


async def handle_duel_reject(query, context):
    """Обработчик отклонения дуэли"""
    chat_id = int(query.data.split("_")[2])

    if chat_id not in duel_state.duels:
        await query.edit_message_text("⚠️ Дуэль уже неактуальна.")
        return

    duel_info = duel_state.duels.pop(chat_id)

    # Проверяем, что нажал именно тот, кому был вызов
    if query.from_user.id != duel_info['target'].id:
        await query.answer("❌ Только вызванный участник может отклонять дуэль!", show_alert=True)
        return

    message = random.choice(SAD_MESSAGES + FUNNY_MESSAGES)

    await query.edit_message_text(
        f"❌ Дуэль отклонена!\n{message}"
    )


async def send_duel_interface(chat_id: int, bot):
    """Отправляет интерфейс дуэли"""
    if chat_id not in duel_state.duels:
        return

    duel_info = duel_state.duels[chat_id]
    current_player = duel_info['caller'] if duel_info['turn'] == 'caller' else duel_info['target']
    opponent = duel_info['target'] if duel_info['turn'] == 'caller' else duel_info['caller']

    current_weapon = duel_info['caller_weapon_info'] if duel_info['turn'] == 'caller' else duel_info[
        'target_weapon_info']
    current_aim = duel_info['caller_aim'] if duel_info['turn'] == 'caller' else duel_info['target_aim']
    current_air_shots = duel_info['caller_air_shots'] if duel_info['turn'] == 'caller' else duel_info[
        'target_air_shots']

    # Определяем максимальный прицел для игрока
    if current_player.username and current_player.username.lower() == "bi1ro":
        max_aim = 5
    else:
        max_aim = 10

    # Проверяем, есть ли ограничения на прицеливание из-за оружия
    if current_weapon.get('no_aim'):
        max_aim = 0

    keyboard = []

    # Добавляем кнопки действий в зависимости от типа оружия
    if current_weapon.get('melee'):
        # Кнопки для ближнего боя
        weapon_effects = duel_state.get_weapon_effect(chat_id, current_player.id)

        if not weapon_effects.get('deceive_used'):
            keyboard.append([InlineKeyboardButton("🃏 Обмануть", callback_data=f"duel_action_{chat_id}_deceive")])

        if not weapon_effects.get('knockdown_used'):
            keyboard.append([InlineKeyboardButton("👊 Сбить с ног", callback_data=f"duel_action_{chat_id}_knockdown")])

        keyboard.append([InlineKeyboardButton("🌀 Сбить прицел", callback_data=f"duel_action_{chat_id}_disrupt")])

        if not weapon_effects.get('alert_used'):
            keyboard.append([InlineKeyboardButton("🛡️ Насторожиться", callback_data=f"duel_action_{chat_id}_alert")])

        keyboard.append([InlineKeyboardButton("⚔️ Атака", callback_data=f"duel_action_{chat_id}_attack")])
        keyboard.append([InlineKeyboardButton("✖️ Прекратить бой", callback_data=f"duel_action_{chat_id}_cancel")])
    else:
        # Кнопки для дальнего боя
        if current_air_shots > 0 and not current_weapon.get('no_air_shot'):
            keyboard.append([InlineKeyboardButton("🎈 Выстрел в воздух", callback_data=f"duel_action_{chat_id}_air")])

        if current_aim < max_aim and not current_weapon.get('no_aim'):
            keyboard.append([InlineKeyboardButton("🎯 Прицелиться (+1)", callback_data=f"duel_action_{chat_id}_aim")])

        keyboard.append([InlineKeyboardButton("🔫 Стрелять", callback_data=f"duel_action_{chat_id}_shoot")])
        keyboard.append(
            [InlineKeyboardButton("🌀 Сбить прицел соперника", callback_data=f"duel_action_{chat_id}_disrupt")])
        keyboard.append([InlineKeyboardButton("✖️ Отменить дуэль", callback_data=f"duel_action_{chat_id}_cancel")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Используем форматированные имена
    current_player_name = format_username(current_player)
    opponent_name = format_username(opponent)

    # Получаем эффекты оружия
    player_effects = duel_state.get_weapon_effect(chat_id, current_player.id)
    opponent_effects = duel_state.get_weapon_effect(chat_id, opponent.id)

    # Добавляем информацию о дополнительных жизнях
    extra_lives_info = ""
    if player_effects.get('survive_hits_remaining', 0) > 0:
        extra_lives_info += f"\n• Гарантированных попаданий осталось: {player_effects['survive_hits_remaining']}"
    if player_effects.get('has_extra_life'):
        extra_lives_info += f"\n• Есть дополнительная жизнь"

    status_text = (
        f"⚔️ ДУЭЛЬ В ПРОЦЕССЕ\n\n"
        f"🎯 Ход: {current_player_name}\n"
        f"🎯 Оружие: {current_weapon['name']}\n"
        f"🎯 Соперник: {opponent_name}\n\n"
        f"📊 Ваша статистика:\n"
        f"• Прицел: {current_aim}/{max_aim}\n"
        f"• Выстрелов в воздух: {current_air_shots}\n"
        f"• Жизней: {duel_info['caller_lives'] if duel_info['turn'] == 'caller' else duel_info['target_lives']}"
        f"{extra_lives_info}\n\n"
        f"🎯 Статистика соперника:\n"
        f"• Прицел: {duel_info['target_aim'] if duel_info['turn'] == 'caller' else duel_info['caller_aim']}\n"
        f"• Жизней: {duel_info['target_lives'] if duel_info['turn'] == 'caller' else duel_info['caller_lives']}\n\n"
        f"⏱️ У вас 5 минут на ход..."
    )

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=status_text,
            reply_markup=reply_markup
        )
    except:
        pass


async def handle_duel_action(query, context):
    """Обработчик действий в дуэли"""
    chat_id = int(query.data.split("_")[2])
    action = query.data.split("_")[3]

    if chat_id not in duel_state.duels:
        await query.answer("⚠️ Дуэль уже завершена!", show_alert=True)
        return

    duel_info = duel_state.duels[chat_id]

    # Проверяем, что нажал текущий игрок
    current_player_id = duel_info['caller'].id if duel_info['turn'] == 'caller' else duel_info['target'].id
    if query.from_user.id != current_player_id:
        await query.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return

    # Обновляем время последнего действия
    duel_info['last_action'] = datetime.now()

    # Получаем информацию об оружии текущего игрока
    if duel_info['turn'] == 'caller':
        player_weapon = duel_info['caller_weapon_info']
        player_username = duel_info['caller'].username
    else:
        player_weapon = duel_info['target_weapon_info']
        player_username = duel_info['target'].username

    # Получаем имена игроков
    shooter = duel_info['caller'] if duel_info['turn'] == 'caller' else duel_info['target']
    target_player = duel_info['target'] if duel_info['turn'] == 'caller' else duel_info['caller']
    shooter_name = format_username(shooter)
    target_name = format_username(target_player)

    # Обработка действий для ближнего боя
    if player_weapon.get('melee'):
        if action == "attack":
            # Атака в ближнем бою
            await handle_melee_attack(chat_id, shooter, target_player, query, context)
            return
        elif action == "deceive":
            # Обмануть
            await handle_deceive(chat_id, shooter, query, context)
            return
        elif action == "knockdown":
            # Сбить с ног
            await handle_knockdown(chat_id, shooter, target_player, query, context)
            return
        elif action == "alert":
            # Насторожиться
            await handle_alert(chat_id, shooter, query, context)
            return
        elif action == "disrupt":
            # Сбить прицел (для ближнего боя)
            if duel_info['turn'] == 'caller':
                duel_info['target_aim'] = 0
            else:
                duel_info['caller_aim'] = 0

            await query.message.edit_text(f"🌀 {shooter_name} сбил прицел соперника!\n\nХод переходит к сопернику...")

            # Меняем ход
            await switch_turn_and_update(chat_id, context.bot)
            return
        elif action == "cancel":
            # Отмена дуэли
            duel_state.duels.pop(chat_id)
            duel_state.clear_weapon_effects(chat_id)
            await query.message.edit_text(f"🏳️ {shooter_name} прекратил бой! Дуэль отменена.")
            return
    else:
        # Обработка действий для дальнего боя
        if action == "air":
            # Выстрел в воздух
            if player_weapon.get('no_air_shot'):
                await query.answer("❌ Это оружие не может стрелять в воздух!", show_alert=True)
                return

            if duel_info['turn'] == 'caller':
                if duel_info['caller_air_shots'] <= 0:
                    await query.answer("❌ У вас не осталось выстрелов в воздух!", show_alert=True)
                    return
                duel_info['caller_air_shots'] -= 1
                duel_info['caller_lives'] += 1
                # Уменьшаем точность после использования
                duel_info['caller_accuracy_modifier'] *= 0.9
            else:
                if duel_info['target_air_shots'] <= 0:
                    await query.answer("❌ У вас не осталось выстрелов в воздух!", show_alert=True)
                    return
                duel_info['target_air_shots'] -= 1
                duel_info['target_lives'] += 1
                duel_info['target_accuracy_modifier'] *= 0.9

            await query.message.edit_text(
                f"🎈 {shooter_name} сделал выстрел в воздух! +1 жизнь\n\nХод переходит к сопернику...")

            # Меняем ход
            await switch_turn_and_update(chat_id, context.bot)
            return

        elif action == "aim":
            # Прицеливание
            if player_weapon.get('no_aim'):
                await query.answer("❌ Это оружие не может прицеливаться!", show_alert=True)
                return

            if duel_info['turn'] == 'caller':
                if duel_info['caller_aim'] < 10:
                    duel_info['caller_aim'] += 1
            else:
                if duel_info['target_aim'] < 10:
                    duel_info['target_aim'] += 1

            await query.message.edit_text(f"🎯 {shooter_name} прицелился!\n\nХод переходит к сопернику...")

            # Меняем ход
            await switch_turn_and_update(chat_id, context.bot)
            return

        elif action == "shoot":
            # Стрельба
            await handle_ranged_attack(chat_id, shooter, target_player, query, context)
            return

        elif action == "disrupt":
            # Сбить прицел соперника
            if duel_info['turn'] == 'caller':
                duel_info['target_aim'] = 0
            else:
                duel_info['caller_aim'] = 0

            await query.message.edit_text(f"🌀 {shooter_name} сбил прицел соперника!\n\nХод переходит к сопернику...")

            # Меняем ход
            await switch_turn_and_update(chat_id, context.bot)
            return

        elif action == "cancel":
            # Отмена дуэли
            duel_state.duels.pop(chat_id)
            duel_state.clear_weapon_effects(chat_id)
            await query.message.edit_text(f"🏳️ {shooter_name} отменил дуэль!")
            return


async def switch_turn_and_update(chat_id: int, bot):
    """Меняет ход и обновляет интерфейс"""
    if chat_id not in duel_state.duels:
        return

    duel_info = duel_state.duels[chat_id]

    # Меняем ход (если не было пропуска хода)
    if duel_info['turn'] == 'caller' and not duel_info.get('caller_skip_turn', False):
        duel_info['turn'] = 'target'
    elif duel_info['turn'] == 'target' and not duel_info.get('target_skip_turn', False):
        duel_info['turn'] = 'caller'

    # Сбрасываем флаг пропуска хода
    if duel_info.get('caller_skip_turn'):
        duel_info['caller_skip_turn'] = False
    if duel_info.get('target_skip_turn'):
        duel_info['target_skip_turn'] = False

    # Обновляем интерфейс
    await send_duel_interface(chat_id, bot)


async def handle_melee_attack(chat_id: int, shooter, target, query, context):
    """Обработка атаки в ближнем бою"""
    duel_info = duel_state.duels[chat_id]
    shooter_name = format_username(shooter)
    target_name = format_username(target)

    # Получаем оружие стрелка
    if duel_info['turn'] == 'caller':
        shooter_weapon = duel_info['caller_weapon_info']
        shooter_effects = duel_state.get_weapon_effect(chat_id, shooter.id)
        target_effects = duel_state.get_weapon_effect(chat_id, target.id)
    else:
        shooter_weapon = duel_info['target_weapon_info']
        shooter_effects = duel_state.get_weapon_effect(chat_id, shooter.id)
        target_effects = duel_state.get_weapon_effect(chat_id, target.id)

    # Определяем шанс попадания
    if shooter_weapon.get('fixed_accuracy'):
        accuracy = shooter_weapon['fixed_accuracy']
    elif shooter.username and shooter.username.lower() == "bi1ro":
        accuracy_table = SPECIAL_ACCURACY
        shooter_aim = duel_info['caller_aim'] if duel_info['turn'] == 'caller' else duel_info['target_aim']
        accuracy = accuracy_table.get(min(shooter_aim, 5), 100)
    else:
        accuracy_table = NORMAL_ACCURACY
        shooter_aim = duel_info['caller_aim'] if duel_info['turn'] == 'caller' else duel_info['target_aim']
        accuracy = accuracy_table.get(min(shooter_aim, 10), 100)

    # Применяем модификатор
    accuracy_modifier = duel_info['caller_accuracy_modifier'] if duel_info['turn'] == 'caller' else duel_info[
        'target_accuracy_modifier']
    final_accuracy = accuracy * accuracy_modifier

    # Проверяем уворот противника
    dodge_chance = 0
    if duel_info['turn'] == 'caller':
        target_weapon = duel_info['target_weapon_info']
    else:
        target_weapon = duel_info['caller_weapon_info']

    # Базовый шанс уворота для ближнего оружия
    if target_weapon.get('melee'):
        dodge_chance = target_weapon.get('base_dodge', 0)

        # Дополнительный шанс уворота из оружия
        if target_weapon.get('dodge_chance'):
            dodge_chance = max(dodge_chance, target_weapon['dodge_chance'])

    # Учитываем бонус настороженности
    if target_effects.get('dodge_bonus'):
        dodge_chance += 5  # +5% к увороту

    # Проверяем уворот
    dodged = random.randint(1, 100) <= dodge_chance

    if dodged:
        result_text = f"🔄 {target_name} уклонился от атаки {shooter_name}!"
        await query.message.edit_text(result_text)
        await switch_turn_and_update(chat_id, context.bot)
        return

    # Проверяем попадание
    hit = random.randint(1, 100) <= final_accuracy

    if not hit:
        # Промах
        result_text = f"🌬️ {shooter_name} промахнулся!"

        # Эффекты при промахе для некоторых оружий
        if shooter_weapon.get('miss_bonus'):
            if duel_info['turn'] == 'caller':
                duel_info['caller_accuracy_modifier'] *= shooter_weapon['miss_bonus']
            else:
                duel_info['target_accuracy_modifier'] *= shooter_weapon['miss_bonus']

        await query.message.edit_text(result_text)
        await switch_turn_and_update(chat_id, context.bot)
        return

    # ПОПАДАНИЕ
    # Проверяем игнорирование второй жизни
    ignore_second_life = False
    if shooter_weapon.get('ignore_extra_lives'):
        ignore_second_life = True
    elif shooter_weapon.get('ignore_second_life_chance'):
        ignore_second_life = random.randint(1, 100) <= shooter_weapon['ignore_second_life_chance']

    # Проверяем, есть ли у цели дополнительные жизни
    target_has_extra_life = target_effects.get('has_extra_life', False)
    target_survive_hits = target_effects.get('survive_hits_remaining', 0)

    if target_survive_hits > 0 and not ignore_second_life:
        # Цель выдерживает попадание
        target_effects['survive_hits_remaining'] -= 1
        result_text = f"💥 {shooter_name} попал в {target_name}, но у того осталось защитных ударов: {target_effects['survive_hits_remaining']}!"
    elif target_has_extra_life and not ignore_second_life:
        # Цель использует дополнительную жизнь
        target_effects['has_extra_life'] = False
        if duel_info['turn'] == 'caller':
            duel_info['target_lives'] = max(0, duel_info['target_lives'] - 1)
        else:
            duel_info['caller_lives'] = max(0, duel_info['caller_lives'] - 1)
        result_text = f"💥 {shooter_name} попал в {target_name}, но у того была дополнительная жизнь!"
    else:
        # Обычное попадание
        if duel_info['turn'] == 'caller':
            duel_info['target_lives'] -= 1
        else:
            duel_info['caller_lives'] -= 1
        result_text = f"💥 {shooter_name} попал в {target_name}!"

    # Эффекты при попадании
    if shooter_weapon.get('gain_life_on_hit'):
        if duel_info['turn'] == 'caller':
            duel_info['caller_lives'] += 1
            result_text += f"\n➕ {shooter_name} получает дополнительную жизнь!"
            shooter_effects['has_extra_life'] = True
        else:
            duel_info['target_lives'] += 1
            result_text += f"\n➕ {target_name} получает дополнительную жизнь!"
            shooter_effects['has_extra_life'] = True

    # Для Самсонова лока - увеличиваем точность после попадания
    if shooter_weapon.get('accuracy_per_hit'):
        hit_count = shooter_effects.get('hit_count', 0) + 1
        shooter_effects['hit_count'] = hit_count
        if hit_count in shooter_weapon['accuracy_per_hit']:
            result_text += f"\n🎯 Точность увеличилась до {shooter_weapon['accuracy_per_hit'][hit_count]}%!"

    await query.message.edit_text(result_text)

    # Проверяем, не закончилась ли дуэль
    await check_duel_end(chat_id, context.bot, query.from_user)

    # Если дуэль продолжается, меняем ход
    if chat_id in duel_state.duels:
        await switch_turn_and_update(chat_id, context.bot)


async def handle_ranged_attack(chat_id: int, shooter, target, query, context):
    """Обработка дальнобойной атаки"""
    duel_info = duel_state.duels[chat_id]
    shooter_name = format_username(shooter)
    target_name = format_username(target)

    # Получаем оружие стрелка
    if duel_info['turn'] == 'caller':
        shooter_weapon = duel_info['caller_weapon_info']
        shooter_effects = duel_state.get_weapon_effect(chat_id, shooter.id)
        target_effects = duel_state.get_weapon_effect(chat_id, target.id)
    else:
        shooter_weapon = duel_info['target_weapon_info']
        shooter_effects = duel_state.get_weapon_effect(chat_id, shooter.id)
        target_effects = duel_state.get_weapon_effect(chat_id, target.id)

    # Определяем точность
    if shooter_weapon.get('fixed_accuracy'):
        accuracy = shooter_weapon['fixed_accuracy']
    elif shooter_weapon.get('first_shot_accuracy') and shooter_effects.get('first_shot', True):
        accuracy = shooter_weapon['first_shot_accuracy']
        shooter_effects['first_shot'] = False
    elif shooter_weapon.get('second_shot_accuracy') and not shooter_effects.get('first_shot', True):
        accuracy = shooter_weapon['second_shot_accuracy']
    elif shooter.username and shooter.username.lower() == "bi1ro":
        accuracy_table = SPECIAL_ACCURACY
        shooter_aim = duel_info['caller_aim'] if duel_info['turn'] == 'caller' else duel_info['target_aim']
        accuracy = accuracy_table.get(min(shooter_aim, 5), 100)
    else:
        accuracy_table = NORMAL_ACCURACY
        shooter_aim = duel_info['caller_aim'] if duel_info['turn'] == 'caller' else duel_info['target_aim']
        accuracy = accuracy_table.get(min(shooter_aim, 10), 100)

    # Для Самсонова лока - используем прогрессивную точность
    if shooter_weapon.get('accuracy_per_hit'):
        hit_count = shooter_effects.get('hit_count', 0)
        accuracy = shooter_weapon['accuracy_per_hit'].get(hit_count, 5)

    # Применяем модификатор
    accuracy_modifier = duel_info['caller_accuracy_modifier'] if duel_info['turn'] == 'caller' else duel_info[
        'target_accuracy_modifier']
    final_accuracy = accuracy * accuracy_modifier

    # Проверяем попадание
    hit = random.randint(1, 100) <= final_accuracy

    if not hit:
        # Промах
        result_text = f"🌬️ {shooter_name} промахнулся!"

        # Для лука Зум - проверяем самоубийство
        if shooter_weapon.get('suicide_if_no_kill') and shooter_effects.get('first_shot_done', False):
            if duel_info['turn'] == 'caller':
                duel_info['caller_lives'] = 0
            else:
                duel_info['target_lives'] = 0
            result_text += f"\n💀 {shooter_name} совершает самоубийство из-за провала миссии!"

        await query.message.edit_text(result_text)

        # Проверяем, не закончилась ли дуэль
        await check_duel_end(chat_id, context.bot, query.from_user)

        # Если дуэль продолжается, меняем ход
        if chat_id in duel_state.duels:
            await switch_turn_and_update(chat_id, context.bot)
        return

    # ПОПАДАНИЕ
    # Отмечаем первый выстрел для лука Зум
    if shooter_weapon.get('first_shot_accuracy'):
        shooter_effects['first_shot_done'] = True

    # Проверяем игнорирование второй жизни
    ignore_second_life = False
    if shooter_weapon.get('ignore_extra_lives'):
        ignore_second_life = True

    # Проверяем, есть ли у цели дополнительные жизни
    target_has_extra_life = target_effects.get('has_extra_life', False)
    target_survive_hits = target_effects.get('survive_hits_remaining', 0)

    if target_survive_hits > 0 and not ignore_second_life:
        # Цель выдерживает попадание
        target_effects['survive_hits_remaining'] -= 1
        result_text = f"💥 {shooter_name} попал в {target_name}, но у того осталось защитных ударов: {target_effects['survive_hits_remaining']}!"
    elif target_has_extra_life and not ignore_second_life:
        # Цель использует дополнительную жизнь
        target_effects['has_extra_life'] = False
        if duel_info['turn'] == 'caller':
            duel_info['target_lives'] = max(0, duel_info['target_lives'] - 1)
        else:
            duel_info['caller_lives'] = max(0, duel_info['caller_lives'] - 1)
        result_text = f"💥 {shooter_name} попал в {target_name}, но у того была дополнительная жизнь!"
    else:
        # Обычное попадание
        if duel_info['turn'] == 'caller':
            duel_info['target_lives'] -= 1
        else:
            duel_info['caller_lives'] -= 1
        result_text = f"💥 {shooter_name} попал в {target_name}!"

    # Для Самсонова лока - увеличиваем счетчик попаданий
    if shooter_weapon.get('accuracy_per_hit'):
        hit_count = shooter_effects.get('hit_count', 0) + 1
        shooter_effects['hit_count'] = hit_count
        if hit_count in shooter_weapon['accuracy_per_hit']:
            result_text += f"\n🎯 Точность увеличилась до {shooter_weapon['accuracy_per_hit'][hit_count]}%!"

    # Эффекты при попадании
    if shooter_weapon.get('gain_life_on_hit'):
        if duel_info['turn'] == 'caller':
            duel_info['caller_lives'] += 1
            result_text += f"\n➕ {shooter_name} получает дополнительную жизнь!"
            shooter_effects['has_extra_life'] = True
        else:
            duel_info['target_lives'] += 1
            result_text += f"\n➕ {target_name} получает дополнительную жизнь!"
            shooter_effects['has_extra_life'] = True

    # Сбрасываем прицел после выстрела
    if duel_info['turn'] == 'caller':
        duel_info['caller_aim'] = 0
    else:
        duel_info['target_aim'] = 0

    await query.message.edit_text(result_text)

    # Проверяем, не закончилась ли дуэль
    await check_duel_end(chat_id, context.bot, query.from_user)

    # Если дуэль продолжается, меняем ход
    if chat_id in duel_state.duels:
        await switch_turn_and_update(chat_id, context.bot)


async def handle_deceive(chat_id: int, shooter, query, context):
    """Обработка обмана в ближнем бою"""
    duel_info = duel_state.duels[chat_id]
    shooter_name = format_username(shooter)

    # Помечаем, что обман использован
    weapon_effects = duel_state.get_weapon_effect(chat_id, shooter.id)
    weapon_effects['deceive_used'] = True

    # Увеличиваем точность для следующей атаки
    if duel_info['turn'] == 'caller':
        duel_info['caller_accuracy_modifier'] *= 1.5
    else:
        duel_info['target_accuracy_modifier'] *= 1.5

    await query.message.edit_text(
        f"🃏 {shooter_name} использует обман! Следующая атака будет точнее.\n\nХод переходит к сопернику...")

    # Меняем ход
    await switch_turn_and_update(chat_id, context.bot)


async def handle_knockdown(chat_id: int, shooter, target, query, context):
    """Обработка сбивания с ног"""
    duel_info = duel_state.duels[chat_id]
    shooter_name = format_username(shooter)
    target_name = format_username(target)

    # Помечаем, что сбивание с ног использован
    weapon_effects = duel_state.get_weapon_effect(chat_id, shooter.id)
    weapon_effects['knockdown_used'] = True

    # Противник пропускает ход
    if duel_info['turn'] == 'caller':
        duel_info['target_skip_turn'] = True
    else:
        duel_info['caller_skip_turn'] = True

    await query.message.edit_text(
        f"👊 {shooter_name} сбивает с ног {target_name}! Противник пропускает следующий ход.\n\nХод переходит к сопернику...")

    # Меняем ход
    await switch_turn_and_update(chat_id, context.bot)


async def handle_alert(chat_id: int, shooter, query, context):
    """Обработка настороженности"""
    duel_info = duel_state.duels[chat_id]
    shooter_name = format_username(shooter)

    # Помечаем, что настороженность использован
    weapon_effects = duel_state.get_weapon_effect(chat_id, shooter.id)
    weapon_effects['alert_used'] = True

    # Увеличиваем шанс уворота
    weapon_effects['dodge_bonus'] = True

    await query.message.edit_text(
        f"🛡️ {shooter_name} настораживается! Шанс уворота увеличен.\n\nХод переходит к сопернику...")

    # Меняем ход
    await switch_turn_and_update(chat_id, context.bot)


async def check_duel_end(chat_id: int, bot, last_action_user):
    """Проверяет окончание дуэли"""
    if chat_id not in duel_state.duels:
        return

    duel_info = duel_state.duels[chat_id]

    winner = None
    loser = None

    if duel_info['caller_lives'] <= 0:
        winner = duel_info['target']
        loser = duel_info['caller']
    elif duel_info['target_lives'] <= 0:
        winner = duel_info['caller']
        loser = duel_info['target']

    if winner and loser:
        # Дуэль окончена
        duel_state.duels.pop(chat_id)
        duel_state.clear_weapon_effects(chat_id)

        # Используем форматированные имена
        winner_name = format_username(winner)
        loser_name = format_username(loser)

        # Получаем оружия победителя и проигравшего
        winner_weapon = duel_info['target_weapon_info'] if winner.id == duel_info['target'].id else duel_info[
            'caller_weapon_info']
        loser_weapon = duel_info['caller_weapon_info'] if loser.id == duel_info['caller'].id else duel_info[
            'target_weapon_info']

        # Награждаем победителя монетами
        coins_won = COINS_PER_WIN
        if winner_weapon.get('coin_multiplier'):
            coins_won *= winner_weapon['coin_multiplier']

        data_store.add_win(winner.id)
        data_store.add_loss(loser.id)

        # Добавляем монеты победителю
        data_store.add_coins(winner.id, coins_won)

        end_message = (
            f"🏆 ДУЭЛЬ ОКОНЧЕНА!\n\n"
            f"🎖️ Победитель: {winner_name}\n"
            f"💀 Проигравший: {loser_name}\n\n"
            f"🎯 Оружие победителя: {winner_weapon['name']}\n"
            f"💰 Награда: +🪙 {coins_won} монет"
        )

        # Если мут включен - мутим проигравшего
        if duel_state.mute_enabled:
            mute_duration = duel_state.mute_duration_minutes

            # Запускаем внутренний мут
            await apply_internal_mute(bot, chat_id, loser.id, loser_name, mute_duration)

            end_message += f"\n\n⏰ {loser_name} получил мут на {mute_duration} минут!"
        else:
            end_message += f"\n\n🟢 Система мута отключена"

        await bot.send_message(
            chat_id=chat_id,
            text=end_message
        )


async def apply_internal_mute(bot, chat_id: int, user_id: int, user_name: str, duration_minutes: int):
    """Применяет внутренний мут пользователю"""
    # Устанавливаем время окончания мута
    mute_until = datetime.now() + timedelta(minutes=duration_minutes)
    duel_state.user_mutes[user_id] = mute_until

    # Сообщаем пользователю
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=f"🔇 {user_name} получил мут на {duration_minutes} минут!"
        )
    except:
        pass

    # Запускаем таймер размута
    task = asyncio.create_task(unmute_user_after_delay(chat_id, user_id, user_name, duration_minutes))
    duel_state.mute_tasks[user_id] = task


async def unmute_user_after_delay(chat_id: int, user_id: int, user_name: str, delay_minutes: int):
    """Автоматический размут пользователя после задержки"""
    await asyncio.sleep(delay_minutes * 60)

    # Удаляем мут
    if user_id in duel_state.user_mutes:
        del duel_state.user_mutes[user_id]

    # Удаляем задачу
    if user_id in duel_state.mute_tasks:
        del duel_state.mute_tasks[user_id]


async def check_message_for_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет сообщения на наличие мута у отправителя"""
    if update.message and update.message.from_user:
        user_id = update.message.from_user.id

        # Проверяем, находится ли пользователь в муте
        if duel_state.is_muted(user_id):
            # Удаляем сообщение пользователя в муте
            try:
                await update.message.delete()

                # Отправляем предупреждение пользователю
                remaining = (duel_state.user_mutes[user_id] - datetime.now()).seconds // 60
                if remaining > 0:
                    warning = await update.message.reply_text(
                        f"🔇 Вы находитесь в муте еще {remaining} минут!"
                    )
                    # Удаляем предупреждение через 5 секунд
                    await asyncio.sleep(5)
                    await warning.delete()

            except Exception as e:
                print(f"Ошибка при удалении сообщения: {e}")
            return


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик всех сообщений для команд дуэли"""
    if update.message and update.message.text:
        text = update.message.text.strip().lower()

        # Обработка команды !дуэль
        if text == "!дуэль":
            await handle_duel_command(update, context)

        # Обработка команды !дуэльныйпрофиль
        elif text == "!дуэльныйпрофиль":
            user_id = update.message.from_user.id
            user_data = data_store.get_user_data(user_id)

            # Получаем текущее оружие
            current_weapon = WEAPONS.get(user_data.current_weapon, WEAPONS["standard_musket"])

            profile_text = (
                f"👤 **ДУЭЛЬНЫЙ ПРОФИЛЬ**\n\n"
                f"Игрок: {format_username(update.message.from_user)}\n"
                f"Серия побед: {user_data.win_streak}\n"
                f"Макс. серия побед: {user_data.max_win_streak}\n"
                f"Всего побед: {user_data.total_wins}\n"
                f"Всего поражений: {user_data.total_losses}\n"
                f"Монет: 🪙 {user_data.coins}\n\n"
                f"🎯 Текущее оружие: {current_weapon['name']}\n"
                f"📦 Оружий в коллекции: {len(user_data.weapons)}\n\n"
                f"👹 **СТАТИСТИКА МОНСТРОВ**\n"
                f"• Обычных убито: {user_data.monster_kills['common']}\n"
                f"• Редких убито: {user_data.monster_kills['rare']}\n"
                f"• Мифических убито: {user_data.monster_kills['mythic']}\n"
                f"• Легендарных убито: {user_data.monster_kills['legendary']}\n"
                f"• Кладов найдено: {user_data.monster_kills['treasure']}"
            )

            keyboard = [
                [InlineKeyboardButton("🛒 Магазин", callback_data="shop_main")],
                [InlineKeyboardButton("👹 Поиск монстра", callback_data="search_monster")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(profile_text, reply_markup=reply_markup, parse_mode='Markdown')

        # Обработка команды !поискмонстра
        elif text == "!поискмонстра":
            # Создаем временный callback запрос для поиска монстра
            class MockQuery:
                def __init__(self, update):
                    self.callback_query = None
                    self.message = update.message
                    self.from_user = update.message.from_user
                    self.data = "search_monster"
                    
                async def answer(self, *args, **kwargs):
                    pass
                    
                async def edit_message_text(self, *args, **kwargs):
                    await self.message.reply_text(*args, **kwargs)
            
            mock_query = MockQuery(update)
            await search_monster_callback(mock_query, context)

        # Обработка ввода времени мута
        elif context.user_data.get('awaiting_mute_input'):
            await handle_mute_input(update, context)


async def start_background_tasks(context):
    """Запуск фоновых задач после инициализации бота"""
    bot = context.bot
    print(f"✅ Бот @{bot.username} успешно подключен!")
    print(
        f"🔗 Ссылка для добавления в чат: https://t.me/{bot.username}?startgroup=true&admin=post_messages+delete_messages+restrict_members")
    # Запускаем задачу проверки неактивных дуэлей
    asyncio.create_task(check_inactive_duels(bot))
    # Запускаем задачу проверки неактивных боев с монстрами
    asyncio.create_task(check_inactive_monster_battles(bot))


async def check_inactive_duels(bot):
    """Проверяет неактивные дуэли"""
    while True:
        await asyncio.sleep(60)  # Проверка каждую минуту

        now = datetime.now()
        duels_to_remove = []

        for chat_id, duel_info in duel_state.duels.items():
            if duel_info['state'] == 'active' and 'last_action' in duel_info:
                if (now - duel_info['last_action']).total_seconds() > 300:  # 5 минут
                    duels_to_remove.append(chat_id)
                    duel_state.clear_weapon_effects(chat_id)

                    message = random.choice(SAD_MESSAGES + FUNNY_MESSAGES)
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"⏰ Дуэль автоматически прекращена из-за бездействия!\n{message}"
                        )
                    except:
                        pass

        for chat_id in duels_to_remove:
            duel_state.duels.pop(chat_id, None)


async def check_inactive_monster_battles(bot):
    """Проверяет неактивные бои с монстрами"""
    while True:
        await asyncio.sleep(60)  # Проверка каждую минуту

        now = datetime.now()
        battles_to_remove = []

        for chat_id, battle_info in duel_state.monster_battles.items():
            if battle_info['state'] == 'active' and 'last_action' in battle_info:
                if (now - battle_info['last_action']).total_seconds() > 300:  # 5 минут
                    battles_to_remove.append(chat_id)

                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"⏰ Бой с монстром автоматически прекращен из-за бездействия!"
                        )
                    except:
                        pass

        for chat_id in battles_to_remove:
            duel_state.end_monster_battle(chat_id)


def main():
    """Основная функция"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("monster", monster_command))

    # Добавляем обработчик для проверки мута перед всеми сообщениями
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, check_message_for_mute), group=-1)

    # Добавляем обработчики callback-запросов (кнопки)
    application.add_handler(CallbackQueryHandler(duel_callback))

    # Добавляем обработчик сообщений (команда !дуэль и ввод мута)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем фоновую задачу проверки неактивных дуэлей через job_queue
    application.job_queue.run_once(start_background_tasks, when=0)

    # Запускаем бота
    print("🤖 Бот запущен и готов к дуэлям!")
    print("⚔️ Для вызова на дуэль: ответьте на сообщение командой '!дуэль'")
    print("👤 Для просмотра профиля: !дуэльныйпрофиль")
    print("👹 Для поиска монстра: /monster, !поискмонстра или кнопка 'Поиск монстра'")
    print("🛒 Магазин оружия доступен через профиль")
    print("⏳ Идет подключение к Telegram...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
