"""
Static exercise library with 80+ exercises.
Each entry contains muscle groups, equipment requirements, MET value,
difficulty level, form instructions, and category.
"""
from typing import Dict, List

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ex(
    muscles: List[str],
    equip: List[str],
    met: float,
    diff: str,
    instructions: str,
    category: str,
) -> dict:
    return {
        "muscle_groups": muscles,
        "equipment": equip,
        "met_value": met,
        "difficulty": diff,
        "instructions": instructions,
        "category": category,
    }


# ---------------------------------------------------------------------------
# Library  (name → attributes)
# ---------------------------------------------------------------------------

_RAW: Dict[str, dict] = {

    # ── CHEST ────────────────────────────────────────────────────────────────
    "Bench Press": _ex(
        ["chest", "triceps", "shoulders"], ["barbell"], 5.0, "intermediate",
        "Lie flat, grip bar just wider than shoulders. Lower bar to mid-chest with "
        "control, elbows at ~45°. Press powerfully back to lockout, keeping wrists stacked.",
        "strength",
    ),
    "Incline Bench Press": _ex(
        ["upper chest", "shoulders", "triceps"], ["barbell"], 5.0, "intermediate",
        "Set bench to 30–45°. Lower bar to upper chest with controlled descent. "
        "Drive through the chest to press bar to lockout. Retract shoulder blades throughout.",
        "strength",
    ),
    "Decline Bench Press": _ex(
        ["lower chest", "triceps"], ["barbell"], 5.0, "intermediate",
        "Secure feet, lie on declined bench. Lower bar to lower chest with control. "
        "Press up and slightly forward, fully contracting the chest at the top.",
        "strength",
    ),
    "Dumbbell Fly": _ex(
        ["chest", "shoulders"], ["dumbbell"], 4.0, "beginner",
        "Lie flat with dumbbells above chest, slight elbow bend. Open arms wide in "
        "an arc until pecs are stretched. Squeeze chest to bring weights back together.",
        "strength",
    ),
    "Incline Dumbbell Fly": _ex(
        ["upper chest", "shoulders"], ["dumbbell"], 4.0, "beginner",
        "Set bench to 30°. With dumbbells above upper chest, arc outward until a "
        "deep stretch is felt. Contract upper pecs to return, avoiding shoulder impingement.",
        "strength",
    ),
    "Cable Fly": _ex(
        ["chest", "shoulders"], ["cable"], 4.5, "beginner",
        "Stand between cable towers, handles at shoulder height. With soft elbows "
        "draw hands together in a hugging motion. Hold peak contraction 1 second.",
        "strength",
    ),
    "Push-up": _ex(
        ["chest", "triceps", "shoulders", "core"], ["bodyweight"], 3.8, "beginner",
        "Start in plank, hands shoulder-width. Lower chest to 1 inch from floor, "
        "elbows at 45°. Push back to full extension while keeping core tight.",
        "strength",
    ),
    "Diamond Push-up": _ex(
        ["triceps", "inner chest"], ["bodyweight"], 4.0, "intermediate",
        "Form a diamond shape with index fingers and thumbs. Lower chest to hands, "
        "keeping elbows close to body. Press up, fully extending arms.",
        "strength",
    ),
    "Wide Push-up": _ex(
        ["chest", "shoulders"], ["bodyweight"], 3.8, "beginner",
        "Place hands 1.5× shoulder width apart. Lower chest until it nearly touches "
        "the floor. Press up through the outer pecs to return.",
        "strength",
    ),
    "Dips": _ex(
        ["chest", "triceps", "shoulders"], ["bodyweight"], 5.0, "intermediate",
        "Grip parallel bars, arms extended. Lower body until upper arms are parallel "
        "to floor. Press back up, leaning slightly forward to target chest.",
        "strength",
    ),
    "Pec Deck Machine": _ex(
        ["chest"], ["machine"], 4.0, "beginner",
        "Sit upright with elbows on pads at chest height. Bring pads together in "
        "front squeezing chest. Return slowly under control.",
        "strength",
    ),

    # ── BACK ─────────────────────────────────────────────────────────────────
    "Pull-up": _ex(
        ["back", "biceps", "core"], ["bodyweight"], 4.5, "intermediate",
        "Dead hang, overhand grip wider than shoulders. Pull chest toward bar, "
        "driving elbows down. Lower under control to full hang.",
        "strength",
    ),
    "Chin-up": _ex(
        ["biceps", "back"], ["bodyweight"], 4.5, "intermediate",
        "Dead hang, underhand grip shoulder-width. Pull chin above bar by driving "
        "elbows back and down. Lower with control.",
        "strength",
    ),
    "Barbell Row": _ex(
        ["back", "biceps", "core"], ["barbell"], 5.0, "intermediate",
        "Hinge to ~45°, grip just outside knees. Pull bar to lower ribs, leading "
        "with elbows. Squeeze lats at top; lower under control.",
        "strength",
    ),
    "Single-arm Dumbbell Row": _ex(
        ["back", "biceps"], ["dumbbell"], 4.5, "beginner",
        "Place one knee and hand on bench. Pull dumbbell to hip, elbow close to "
        "body. At top, rotate and squeeze lat. Lower slowly.",
        "strength",
    ),
    "T-Bar Row": _ex(
        ["back", "biceps"], ["barbell"], 5.0, "intermediate",
        "Straddle bar, hinge forward. Pull bar to chest, elbows flared ~45°. "
        "Squeeze shoulder blades at top, then lower with control.",
        "strength",
    ),
    "Lat Pulldown": _ex(
        ["back", "biceps"], ["cable", "machine"], 4.5, "beginner",
        "Grip bar wider than shoulders, lean back slightly. Pull bar to upper chest, "
        "driving elbows down and back. Return slowly to full stretch.",
        "strength",
    ),
    "Seated Cable Row": _ex(
        ["back", "biceps", "core"], ["cable"], 4.5, "beginner",
        "Sit upright, knees soft, grip neutral handle. Pull to lower ribs, "
        "squeezing shoulder blades. Hinge slightly forward to stretch lats on return.",
        "strength",
    ),
    "Deadlift": _ex(
        ["back", "glutes", "hamstrings", "core"], ["barbell"], 6.0, "advanced",
        "Stand over bar, hip-width stance. Hinge and grip just outside legs. "
        "Drive through floor, extending hips and knees simultaneously. Lock out "
        "standing tall; hinge back to lower.",
        "strength",
    ),
    "Rack Pull": _ex(
        ["back", "glutes", "traps"], ["barbell"], 5.5, "intermediate",
        "Set safety bars at knee height. Grip bar, brace hard. Pull by extending "
        "hips and knees, finishing with full hip extension. Lower controlled.",
        "strength",
    ),
    "Face Pull": _ex(
        ["rear delts", "upper back", "rotator cuff"], ["cable"], 3.5, "beginner",
        "Set cable at face height with rope. Pull rope to forehead, elbows flared "
        "high and wide. Externally rotate wrists at end. Return slowly.",
        "strength",
    ),
    "Hyperextension": _ex(
        ["lower back", "glutes", "hamstrings"], ["machine", "bodyweight"], 4.0, "beginner",
        "Lock ankles in pad, hinge at waist, lower torso toward floor. "
        "Squeeze glutes to rise until body is straight. Avoid hyperextending.",
        "strength",
    ),

    # ── SHOULDERS ────────────────────────────────────────────────────────────
    "Overhead Press": _ex(
        ["shoulders", "triceps", "upper back"], ["barbell"], 5.0, "intermediate",
        "Grip bar just outside shoulders at collarbone. Press overhead until elbows "
        "lock, moving head back through the bar's path. Lower to clavicle under control.",
        "strength",
    ),
    "Dumbbell Shoulder Press": _ex(
        ["shoulders", "triceps"], ["dumbbell"], 4.5, "beginner",
        "Sit or stand, dumbbells at ear level, elbows 90°. Press overhead until "
        "nearly touching at top. Lower slowly to start position.",
        "strength",
    ),
    "Arnold Press": _ex(
        ["shoulders", "triceps"], ["dumbbell"], 4.5, "intermediate",
        "Start with dumbbells at chin, palms facing you. Press up while rotating "
        "palms outward, finishing with palms forward overhead. Reverse on descent.",
        "strength",
    ),
    "Lateral Raise": _ex(
        ["lateral deltoids"], ["dumbbell"], 3.5, "beginner",
        "Stand with dumbbells at sides, slight elbow bend. Raise arms to shoulder "
        "height in a wide arc, leading with pinkies. Lower slowly over 3 seconds.",
        "strength",
    ),
    "Cable Lateral Raise": _ex(
        ["lateral deltoids"], ["cable"], 3.5, "beginner",
        "Stand beside cable, cross-body grip. Raise arm to shoulder height keeping "
        "elbow slightly bent. Resist the cable on the way down.",
        "strength",
    ),
    "Front Raise": _ex(
        ["front deltoids", "upper chest"], ["dumbbell"], 3.5, "beginner",
        "Stand with dumbbells at thighs, palms down. Raise one or both arms to "
        "shoulder height. Lower with control, avoiding body sway.",
        "strength",
    ),
    "Rear Delt Fly": _ex(
        ["rear deltoids", "upper back"], ["dumbbell"], 3.5, "beginner",
        "Hinge forward 45–90°. With soft elbows, raise arms out to sides until "
        "level with torso. Squeeze rear delts at top, lower slowly.",
        "strength",
    ),
    "Shrugs": _ex(
        ["traps"], ["barbell", "dumbbell"], 4.0, "beginner",
        "Hold weight at sides, arms straight. Elevate shoulders straight up toward "
        "ears as high as possible. Hold 1 second, then slowly lower.",
        "strength",
    ),
    "Upright Row": _ex(
        ["traps", "shoulders"], ["barbell", "dumbbell"], 4.0, "intermediate",
        "Grip bar narrow, hands close together. Pull bar straight up to chin, "
        "elbows flared high. Lower under control; avoid if shoulder impingement exists.",
        "strength",
    ),

    # ── ARMS ─────────────────────────────────────────────────────────────────
    "Barbell Bicep Curl": _ex(
        ["biceps", "forearms"], ["barbell"], 3.5, "beginner",
        "Stand tall, underhand grip shoulder-width. Curl bar to shoulder height "
        "by flexing elbows only. Lower slowly, fully extending at bottom.",
        "strength",
    ),
    "Dumbbell Bicep Curl": _ex(
        ["biceps", "forearms"], ["dumbbell"], 3.5, "beginner",
        "Alternating or simultaneous, curl from full extension to full contraction. "
        "Supinate wrist at top to maximize bicep peak. Lower with control.",
        "strength",
    ),
    "Hammer Curl": _ex(
        ["biceps", "brachialis", "forearms"], ["dumbbell"], 3.5, "beginner",
        "Neutral grip (thumbs up). Curl dumbbells to shoulder height keeping "
        "wrists neutral throughout. Lower slowly, feeling brachialis stretch.",
        "strength",
    ),
    "Preacher Curl": _ex(
        ["biceps"], ["barbell", "dumbbell", "machine"], 3.5, "beginner",
        "Brace upper arms on angled pad. Curl from full extension to full "
        "contraction, focusing on peak squeeze. Lower under full control.",
        "strength",
    ),
    "Concentration Curl": _ex(
        ["biceps"], ["dumbbell"], 3.0, "beginner",
        "Sit, brace working arm's elbow on inner thigh. Curl slowly to shoulder. "
        "Squeeze hard at top, lower all the way. Isolates the bicep peak.",
        "strength",
    ),
    "EZ Bar Curl": _ex(
        ["biceps", "forearms"], ["barbell"], 3.5, "beginner",
        "Grip EZ bar at angled grip, shoulder-width. Curl to shoulders, keeping "
        "elbows tucked at sides. Lower fully to stretch biceps.",
        "strength",
    ),
    "Tricep Pushdown": _ex(
        ["triceps"], ["cable"], 3.5, "beginner",
        "Grip bar or rope at chest height, elbows pinned to sides. Push down "
        "to full extension, squeezing triceps. Slowly return to start.",
        "strength",
    ),
    "Skull Crusher": _ex(
        ["triceps"], ["barbell", "dumbbell"], 4.0, "intermediate",
        "Lie flat, arms extended above chest. Hinge only at elbows, lowering "
        "weight toward forehead. Extend back to start without flaring elbows.",
        "strength",
    ),
    "Close Grip Bench Press": _ex(
        ["triceps", "chest"], ["barbell"], 5.0, "intermediate",
        "Grip bar shoulder-width, hands close. Lower to lower chest with elbows "
        "tucked. Press to full lockout, feeling triceps work throughout.",
        "strength",
    ),
    "Overhead Tricep Extension": _ex(
        ["triceps"], ["dumbbell", "cable"], 3.5, "beginner",
        "Hold dumbbell or rope overhead with elbows pointing up. Hinge at elbows "
        "to lower weight behind head. Extend fully at top, squeezing triceps.",
        "strength",
    ),

    # ── LEGS ─────────────────────────────────────────────────────────────────
    "Barbell Squat": _ex(
        ["quadriceps", "glutes", "hamstrings", "core"], ["barbell"], 5.0, "intermediate",
        "Bar on upper traps, stance just wider than hips. Break at hips and knees "
        "simultaneously. Descend until thighs are parallel. Drive through mid-foot to stand.",
        "strength",
    ),
    "Goblet Squat": _ex(
        ["quadriceps", "glutes", "core"], ["dumbbell"], 5.0, "beginner",
        "Hold dumbbell at chest, feet shoulder-width. Squat deep, keeping "
        "elbows inside knees. Drive through heels to stand. Great for form practice.",
        "strength",
    ),
    "Romanian Deadlift": _ex(
        ["hamstrings", "glutes", "lower back"], ["barbell", "dumbbell"], 5.0, "intermediate",
        "Stand with bar at hip height. Hinge at hips pushing them back, bar "
        "slides down thighs until deep hamstring stretch. Drive hips forward to stand.",
        "strength",
    ),
    "Sumo Deadlift": _ex(
        ["glutes", "hamstrings", "inner thighs", "back"], ["barbell"], 6.0, "intermediate",
        "Wide stance, toes pointed out, grip inside legs. Keep chest tall, push "
        "knees out over toes. Pull bar close to body, extending hips at lockout.",
        "strength",
    ),
    "Leg Press": _ex(
        ["quadriceps", "glutes", "hamstrings"], ["machine"], 5.0, "beginner",
        "Feet shoulder-width on platform. Unlock and lower sled until knees at 90°. "
        "Press through heels to full extension without locking knees.",
        "strength",
    ),
    "Hack Squat": _ex(
        ["quadriceps", "glutes"], ["machine"], 5.0, "intermediate",
        "Shoulders under pads, feet mid-platform. Lower to 90° knee angle. "
        "Drive through platform, extending fully without locking out.",
        "strength",
    ),
    "Lunges": _ex(
        ["quadriceps", "glutes", "hamstrings"], ["bodyweight", "dumbbell"], 4.5, "beginner",
        "Step forward, lower rear knee toward floor. Front knee tracks over foot, "
        "torso upright. Push through front heel to return. Alternate legs.",
        "strength",
    ),
    "Walking Lunges": _ex(
        ["quadriceps", "glutes", "hamstrings", "core"], ["bodyweight", "dumbbell"], 5.0, "intermediate",
        "Step forward into lunge, then drive through front heel to bring rear foot "
        "forward into next step. Maintain upright torso throughout.",
        "strength",
    ),
    "Bulgarian Split Squat": _ex(
        ["quadriceps", "glutes"], ["dumbbell", "barbell"], 5.0, "intermediate",
        "Rear foot elevated on bench, front foot forward. Lower rear knee toward "
        "floor, front shin vertical. Drive through front heel to stand.",
        "strength",
    ),
    "Leg Curl": _ex(
        ["hamstrings"], ["machine"], 4.0, "beginner",
        "Lie prone, pad on lower calves. Curl heels toward glutes, squeezing "
        "hamstrings at top. Lower slowly over 3 seconds to full extension.",
        "strength",
    ),
    "Leg Extension": _ex(
        ["quadriceps"], ["machine"], 4.0, "beginner",
        "Sit upright, pad on lower shins. Extend knees to full lockout, squeezing "
        "quads hard at top. Lower slowly, stopping just before plates touch.",
        "strength",
    ),
    "Calf Raise": _ex(
        ["calves"], ["machine", "bodyweight"], 3.5, "beginner",
        "Stand on edge of platform, balls of feet only. Rise on toes as high as "
        "possible, hold 1 second. Lower until calves are fully stretched.",
        "strength",
    ),
    "Step-ups": _ex(
        ["quadriceps", "glutes"], ["bodyweight", "dumbbell"], 4.5, "beginner",
        "Place one foot on box or bench. Drive through that heel to stand on box. "
        "Lower the other foot back down under control. Alternate legs.",
        "strength",
    ),

    # ── CORE ─────────────────────────────────────────────────────────────────
    "Plank": _ex(
        ["core", "shoulders", "glutes"], ["bodyweight"], 3.0, "beginner",
        "Forearms on floor, elbows under shoulders. Keep body in straight line "
        "from head to heels. Brace abs hard; breathe normally. Avoid sagging hips.",
        "strength",
    ),
    "Side Plank": _ex(
        ["obliques", "core"], ["bodyweight"], 3.0, "beginner",
        "Lie on side, prop on forearm. Stack feet or stagger them. Raise hips "
        "forming a straight line. Hold, then repeat on other side.",
        "strength",
    ),
    "Crunches": _ex(
        ["core"], ["bodyweight"], 3.5, "beginner",
        "Lie on back, knees bent. Place hands behind head for support only. "
        "Curl shoulders off floor by contracting abs. Lower under control.",
        "strength",
    ),
    "Bicycle Crunch": _ex(
        ["core", "obliques"], ["bodyweight"], 3.8, "beginner",
        "Lie back, hands behind head. Alternately bring opposite elbow to knee "
        "while extending the other leg. Rotate through the torso, not just elbows.",
        "strength",
    ),
    "Russian Twist": _ex(
        ["obliques", "core"], ["bodyweight", "dumbbell"], 3.5, "beginner",
        "Sit with knees bent, lean back 45°. Rotate torso side to side, touching "
        "weight or hands to the floor. Keep feet elevated for extra difficulty.",
        "strength",
    ),
    "Leg Raise": _ex(
        ["lower core", "hip flexors"], ["bodyweight"], 3.5, "intermediate",
        "Lie flat, hands under lower back. Keeping legs straight, raise to 90°. "
        "Lower slowly, stopping 1 inch from floor to maintain tension.",
        "strength",
    ),
    "Hanging Leg Raise": _ex(
        ["core", "hip flexors"], ["bodyweight"], 4.0, "advanced",
        "Dead hang from bar. Brace core and raise legs to 90° or above. "
        "Avoid swinging — control the movement both up and down.",
        "strength",
    ),
    "Dead Bug": _ex(
        ["core", "lower back"], ["bodyweight"], 3.0, "beginner",
        "Lie on back, arms up, knees at 90°. Simultaneously lower opposite arm "
        "and leg toward floor while pressing lower back into floor. Return; alternate.",
        "strength",
    ),
    "Ab Wheel": _ex(
        ["core", "shoulders", "lats"], ["bodyweight"], 4.5, "advanced",
        "Kneel, hands on wheel. Roll out, keeping hips down and core tight. "
        "Contract abs forcefully to roll back to start. Progress distance gradually.",
        "strength",
    ),

    # ── CARDIO ───────────────────────────────────────────────────────────────
    "Running": _ex(
        ["legs", "core", "cardiovascular"], ["bodyweight"], 8.0, "beginner",
        "Maintain upright posture, slight forward lean. Land mid-foot, not heel. "
        "Arms swing forward-back at ~90°. Breathe rhythmically at conversational pace.",
        "cardio",
    ),
    "Cycling": _ex(
        ["quadriceps", "hamstrings", "cardiovascular"], ["machine"], 7.0, "beginner",
        "Adjust seat so knee is slightly bent at bottom of stroke. Pedal in circles "
        "pushing down and pulling up. Maintain a cadence of 70–100 rpm.",
        "cardio",
    ),
    "Jump Rope": _ex(
        ["calves", "shoulders", "cardiovascular"], ["bodyweight"], 11.0, "intermediate",
        "Jump just high enough to clear the rope, landing on balls of feet. "
        "Keep elbows at sides, wrists doing the rotation. Start slow; build speed.",
        "cardio",
    ),
    "Burpees": _ex(
        ["full body", "cardiovascular"], ["bodyweight"], 8.0, "intermediate",
        "Drop hands, jump feet back to push-up position. Perform push-up. "
        "Jump feet to hands, then explode up with arms overhead. Land softly.",
        "hiit",
    ),
    "Mountain Climbers": _ex(
        ["core", "shoulders", "cardiovascular"], ["bodyweight"], 5.0, "beginner",
        "Start in plank. Drive alternating knees to chest rapidly, keeping hips "
        "level. Maintain plank alignment throughout the movement.",
        "hiit",
    ),
    "Box Jumps": _ex(
        ["glutes", "quadriceps", "calves", "cardiovascular"], ["bodyweight"], 6.5, "intermediate",
        "Stand before box, quarter-squat, swing arms and jump. Land softly on "
        "mid-foot with knees bent. Step down (don't jump) to protect joints.",
        "hiit",
    ),
    "Rowing Machine": _ex(
        ["back", "legs", "core", "cardiovascular"], ["machine"], 7.0, "beginner",
        "Drive through legs first, then lean back, then pull handle to lower "
        "ribs. Return in reverse: arms, lean forward, bend knees. 60% legs, 20% lean, 20% arms.",
        "cardio",
    ),
    "Stair Climber": _ex(
        ["glutes", "quadriceps", "cardiovascular"], ["machine"], 7.0, "beginner",
        "Keep torso upright; don't lean heavily on handles. Take full steps, "
        "pressing through the heel. Maintain a steady sustainable pace.",
        "cardio",
    ),
    "High Knees": _ex(
        ["hip flexors", "core", "cardiovascular"], ["bodyweight"], 7.0, "beginner",
        "Run in place, driving knees to hip height. Pump arms in sync with legs. "
        "Land on balls of feet and immediately drive the next knee up.",
        "hiit",
    ),
    "Battle Ropes": _ex(
        ["shoulders", "core", "cardiovascular"], ["bodyweight"], 9.0, "intermediate",
        "Hold rope ends, slight squat stance. Create alternating waves moving the "
        "full rope length. Keep core tight; vary patterns every 30 seconds.",
        "hiit",
    ),
    "Elliptical Training": _ex(
        ["full body", "cardiovascular"], ["machine"], 5.5, "beginner",
        "Stand upright, push and pull handles while pedaling in a smooth oval. "
        "Keep weight in heels, not toes. Adjust resistance to maintain effort.",
        "cardio",
    ),

    # ── FULL BODY ─────────────────────────────────────────────────────────────
    "Turkish Get-up": _ex(
        ["full body", "core", "shoulders"], ["dumbbell"], 5.5, "advanced",
        "Start lying down, bell overhead in locked arm. Follow the 7-step sequence: "
        "roll to elbow, prop on hand, bridge hips, sweep leg through, lunge, stand. "
        "Reverse to descend. Keep eyes on the bell throughout.",
        "strength",
    ),
    "Clean and Press": _ex(
        ["full body", "shoulders", "back", "legs"], ["barbell", "dumbbell"], 7.0, "advanced",
        "Deadlift bar to knees, then explosively shrug and pull under bar into "
        "a front rack. Dip and drive overhead. Lower to rack, then floor.",
        "strength",
    ),
    "Kettlebell Swing": _ex(
        ["glutes", "hamstrings", "back", "core"], ["dumbbell"], 6.5, "intermediate",
        "Hike bell back between legs. Snap hips forward explosively, driving bell "
        "to shoulder height with straight arms. Let it fall back, hinge again.",
        "hiit",
    ),
    "Thrusters": _ex(
        ["quadriceps", "glutes", "shoulders", "core"], ["barbell", "dumbbell"], 7.0, "advanced",
        "Hold bar in front rack, squat deep. As you stand, use the momentum to "
        "press bar overhead to full lockout. Return to rack at top of descent.",
        "hiit",
    ),
    "Push Press": _ex(
        ["shoulders", "triceps", "legs"], ["barbell", "dumbbell"], 6.0, "intermediate",
        "Bar in front rack, slight knee dip. Drive through legs, use momentum to "
        "press bar overhead. Lock out arms, lower back to rack under control.",
        "strength",
    ),
    "Power Clean": _ex(
        ["full body", "back", "legs"], ["barbell"], 7.0, "advanced",
        "Pull bar from floor like a deadlift, then explosively extend hips and "
        "shrug. Pull yourself under bar into a quarter-squat catch. Stand up.",
        "strength",
    ),
    "Dumbbell Snatch": _ex(
        ["full body", "shoulders"], ["dumbbell"], 6.5, "advanced",
        "Start with dumbbell between feet. Drive hips, shrug and pull bell overhead "
        "in one fluid motion, punching up under it. Lock out arm at top.",
        "strength",
    ),
    "Barbell Complex": _ex(
        ["full body"], ["barbell"], 7.5, "advanced",
        "Perform 6 reps each of: deadlift, hang clean, front squat, overhead press, "
        "back squat — without setting bar down. Rest 60–90 s between rounds.",
        "hiit",
    ),
    "Man Makers": _ex(
        ["full body", "chest", "shoulders", "core"], ["dumbbell"], 7.0, "advanced",
        "Start in push-up position with dumbbells. Push-up, row each arm, jump feet "
        "to hands, clean to shoulders, then press overhead. That's one rep.",
        "hiit",
    ),
}

# Attach the name key to every record
EXERCISE_LIBRARY: Dict[str, dict] = {
    name: {"name": name, **attrs} for name, attrs in _RAW.items()
}


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_exercises_by_muscle(muscle: str) -> List[dict]:
    """Return exercises that train the given muscle (case-insensitive partial match)."""
    muscle_lower = muscle.lower()
    return [
        ex for ex in EXERCISE_LIBRARY.values()
        if any(muscle_lower in mg.lower() for mg in ex["muscle_groups"])
    ]


def get_exercises_by_equipment(equipment: List[str]) -> List[dict]:
    """Return exercises achievable with the given equipment list.

    Bodyweight exercises are always included since they require no gear.
    An exercise matches if at least one of its equipment items is in the
    provided list.
    """
    available = {e.lower() for e in equipment} | {"bodyweight"}
    return [
        ex for ex in EXERCISE_LIBRARY.values()
        if any(eq.lower() in available for eq in ex["equipment"])
    ]


def calculate_calories_burned(
    exercise_name: str,
    duration_mins: float,
    weight_kg: float,
) -> float:
    """Estimate calories burned using MET × weight_kg × duration_hours."""
    ex = EXERCISE_LIBRARY.get(exercise_name)
    met = ex["met_value"] if ex else 5.0  # default MET if exercise not found
    return round(met * weight_kg * (duration_mins / 60.0), 1)
