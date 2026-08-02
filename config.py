"""
SHADOW CASE — configuration and tunable constants.
"""

import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "shadowcase.db")

# --- starting stats for a new case -----------------------------------------
START_STAMINA = 100
START_HUNGER = 100
START_THIRST = 100
START_HEALTH = 100
START_REPUTATION = 50
START_TRUST = 50
MAX_DAYS = 7

# --- action costs -------------------------------------------------------- #
SEARCH_STAMINA_COST = 15
SEARCH_HUNGER_COST = 8
SEARCH_THIRST_COST = 10

TALK_STAMINA_COST = 5
TALK_HUNGER_COST = 3
TALK_THIRST_COST = 3

LOCKPICK_FAIL_STAMINA_COST = 5
ASSEMBLY_FAIL_STAMINA_COST = 5

STARVATION_HEALTH_LOSS = 10

REST_STAMINA_GAIN = 60
REST_HUNGER_GAIN = 35
REST_THIRST_GAIN = 35

TURNS_PER_DAY = 3

# --- suspects config ------------------------------------------------------ #
SUSPECTS_PER_CASE = 4
LOCATIONS_PER_CASE = 4
