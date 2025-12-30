"""Random prompts for the Telemess game."""

import random

# Fun, action-oriented prompts that are easy to draw but can go hilariously wrong
PROMPTS = [
    # Food & Cooking
    "cooking pancakes",
    "eating spaghetti",
    "burning toast",
    "catching a pizza",
    "drinking hot soup",
    "making a sandwich",
    "juggling eggs",
    "stealing cookies",
    # Animals doing things
    "cat riding a bicycle",
    "dog playing piano",
    "elephant taking a bath",
    "penguin on a skateboard",
    "monkey playing tennis",
    "fish driving a car",
    "bird lifting weights",
    "frog doing yoga",
    # People & Actions
    "dancing in the rain",
    "sleeping on a cloud",
    "running from bees",
    "catching butterflies",
    "fighting a pirate",
    "hugging a cactus",
    "surfing on a wave",
    "climbing a mountain",
    # Silly scenarios
    "alien disco party",
    "robot making coffee",
    "wizard ordering pizza",
    "ninja hiding in bushes",
    "superhero doing laundry",
    "vampire at the beach",
    "ghost using a computer",
    "dinosaur in a suit",
    # Everyday chaos
    "stuck in traffic",
    "losing your keys",
    "phone running out of battery",
    "stepping on lego",
    "missing the bus",
    "spilling coffee",
    "oversleeping alarm",
    "waiting in line",
    # Sports & Activities
    "bowling strike",
    "failed basketball dunk",
    "swimming with sharks",
    "winning a race",
    "learning to ski",
    "first day at gym",
    "catching a frisbee",
    "jumping on trampoline",
    # Fantasy & Sci-fi
    "dragon barbecue",
    "unicorn traffic jam",
    "time travel mishap",
    "space picnic",
    "underwater tea party",
    "flying carpet race",
    "magic spell gone wrong",
    "meeting your clone",
    # Absurd combinations
    "birthday party on the moon",
    "office meeting with animals",
    "grandma as a DJ",
    "baby fighting monsters",
    "teacher as a rockstar",
    "dentist at a circus",
    "chef in a spaceship",
    "farmer on a rollercoaster",
]


def get_random_prompt() -> str:
    """Get a random prompt from the list."""
    return random.choice(PROMPTS)


def get_random_prompts(count: int) -> list[str]:
    """Get multiple unique random prompts."""
    if count >= len(PROMPTS):
        return random.sample(PROMPTS, len(PROMPTS))
    return random.sample(PROMPTS, count)
