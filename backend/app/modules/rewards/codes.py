from enum import StrEnum


class BananaTransactionType(StrEnum):
    DAILY_REWARD = "DAILY_REWARD"
    WORKOUT_COMPLETED = "WORKOUT_COMPLETED"
    WORKOUT_PARTIAL = "WORKOUT_PARTIAL"
    WORKOUT_SAFETY_STOPPED = "WORKOUT_SAFETY_STOPPED"
    WORKOUT_DAILY_QUEST = "WORKOUT_DAILY_QUEST"
    HOUSE_FEED = "HOUSE_FEED"
    HOUSE_ITEM_PURCHASE = "HOUSE_ITEM_PURCHASE"
    MINI_GAME = "MINI_GAME"
    HOUSE_BONDING_QUEST = "HOUSE_BONDING_QUEST"


class BananaSpendActionCode(StrEnum):
    FEED_MASCOT = "FEED_MASCOT"
    PURCHASE_HOUSE_ITEM = "PURCHASE_HOUSE_ITEM"


DAILY_REWARD_BANANAS = 15
WORKOUT_COMPLETED_BANANAS = 30
WORKOUT_PARTIAL_BANANAS = 15
WORKOUT_DAILY_QUEST_BANANAS = 10
# The house bonding quest. Claimed once a local day like the daily reward, which
# it mirrors: the server cannot observe petting, so it pays a fixed amount on
# request rather than verifying the quest. The exposure is the same shape and the
# same size as the existing daily claim -- one fixed payout a day.
HOUSE_BONDING_QUEST_BANANAS = 5
# The house mini-game pays out in proportion to the score the player actually
# reached. The score arrives from the client, so the server decides the payout
# from it rather than accepting an amount, bounds it, and pays at most once a
# day -- the same limit the house tile advertises.
MINI_GAME_POINTS_PER_BANANA = 2
MINI_GAME_MAX_BANANAS = 25
# A 30s round spawns a banana every 650ms, so a flawless run scores about 46.
# Anything past this is not a score the game can produce; the request is refused
# instead of being silently clamped, so a broken client is visible.
MINI_GAME_MAX_SCORE = 200
HOUSE_FEED_COST = 10
HOUSE_ITEM_COSTS: dict[str, int] = {
    "yoga_mat": 20,
    "dumbbell": 20,
    "plant": 25,
    "cushion": 25,
    "lamp": 30,
    "star_frame": 35,
    "window": 35,
}
