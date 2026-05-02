"""Hardcoded run presets — one-click starting configurations.

Every preset is tuned for indie iOS / iPadOS apps published on the App Store.
Each one leans into a specific Apple-platform leverage point (HealthKit,
Apple Pencil, Widgets/Watch, ARKit/Vision, Shortcuts, etc.) so the agent's
ideas actually exploit what makes iOS native apps strong vs. cross-platform.

Ordering goes from broad → specialized: lifestyle/productivity/wellness up
top, more niche / platform-specific picks toward the bottom.
"""

from __future__ import annotations

from factory.ideation.run_config import RunConfig

PRESETS: dict[str, RunConfig] = {
    # ───── Broad consumer categories ─────────────────────────────────────
    "Daily-use consumer (default)": RunConfig(
        focus_prompt=(
            "Mobile-first iOS apps people open every single day on their iPhone. "
            "Strong native feel, smooth animations, solid Lock Screen + Home Screen "
            "widget support. Low-friction onboarding (no signup wall on first launch). "
            "Freemium with a subscription paywall is the dominant model."
        ),
        niche_seeds=[
            "habit tracker", "focus timer", "ai journal",
            "sleep tracker", "mood tracker", "gratitude journal",
            "water tracker", "meditation",
        ],
        subreddits=[
            "productivity", "getdisciplined", "GetMotivated",
            "iphone", "ios", "apps", "AppHookup",
        ],
        avoid="cross-platform-first apps, anything that needs a web companion to be useful",
        target_idea_count=4,
        min_score=55,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="general iPhone users · daily app habit",
        monetization_preference="freemium",
    ),
    "Productivity & focus": RunConfig(
        focus_prompt=(
            "iOS productivity apps for adults: todo lists, calendars, time-"
            "blocking, focus timers, habit formation, daily planning. Lean "
            "into Lock Screen widgets, Focus modes, Live Activities and Apple "
            "Watch reminders to keep users on track. Includes neurodiverse-"
            "friendly tools (ADHD, executive function), but doesn't have to."
        ),
        niche_seeds=[
            "todo app", "calendar app", "time blocking",
            "pomodoro", "focus timer", "habit tracker",
            "daily planner", "weekly review",
        ],
        subreddits=[
            "productivity", "getdisciplined", "ADHD",
            "GetMotivated", "NotionApp", "ObsidianMD",
        ],
        avoid="generic empty to-do lists, gamification fluff",
        target_idea_count=4,
        min_score=58,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="working adults seeking better focus or organization",
        monetization_preference="freemium",
    ),
    "Wellness & HealthKit": RunConfig(
        focus_prompt=(
            "iOS apps that integrate deeply with Apple Health (HealthKit), Apple "
            "Watch sensors, or sleep / cycle tracking. Personal physical or mental "
            "wellbeing — measurable, low-friction daily use. Stay out of medical-"
            "device territory: nothing FDA-regulated, no diagnosis, no prescription."
        ),
        niche_seeds=[
            "sleep tracker", "hydration tracker", "breathwork",
            "period tracker", "anxiety journal", "fasting tracker",
            "heart rate variability", "posture reminder",
        ],
        subreddits=[
            "fitness", "loseit", "intermittentfasting", "Meditation",
            "anxiety", "ADHD", "getdisciplined", "AppleWatch",
        ],
        avoid="medical diagnosis, prescription tracking, anything FDA-regulated",
        target_idea_count=4,
        min_score=58,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="health-conscious adults 25–45, Apple Watch owners",
        monetization_preference="freemium",
    ),
    "Photo & video": RunConfig(
        focus_prompt=(
            "iOS photo and video tools: editors, filter packs, organizers, "
            "slow-motion / time-lapse, batch processing, color grading. Use "
            "the Photos library API, Live Photos, on-device ML for tagging. "
            "Premium one-time pricing or freemium with paid filter packs both work."
        ),
        niche_seeds=[
            "photo editor", "video editor", "photo organizer",
            "presets", "color grading", "slow motion",
            "batch resize", "photo collage",
        ],
        subreddits=[
            "iphone", "photography", "iOSProgramming",
            "AppHookup", "videography", "Filmmakers",
        ],
        avoid="social photo sharing, generic Instagram-style apps",
        target_idea_count=3,
        min_score=60,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="photo / video enthusiasts shooting on iPhone",
        monetization_preference="freemium",
    ),
    "Education & learning": RunConfig(
        focus_prompt=(
            "iOS learning apps for adults or kids — language learning, flashcards, "
            "study tools, exam prep, skill-building. Spaced repetition plus native "
            "iOS notification scheduling are real leverage. Freemium with a "
            "subscription paywall is the dominant model in this category."
        ),
        niche_seeds=[
            "language learning", "flashcards", "study app",
            "exam prep", "vocabulary builder", "spaced repetition",
            "kids learning", "math tutor",
        ],
        subreddits=[
            "languagelearning", "Anki", "GetStudying",
            "ipad", "productivity", "education",
        ],
        avoid="generic textbook PDFs, content-license-heavy apps",
        target_idea_count=4,
        min_score=58,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="adult learners, students, parents of school-age kids",
        monetization_preference="freemium",
    ),
    "Finance & money": RunConfig(
        focus_prompt=(
            "iOS personal-finance apps: budget tracking, expense logging, "
            "investment portfolio, savings goals, subscription tracker, debt "
            "payoff. Privacy matters — on-device-first beats Plaid/cloud sync "
            "as a positioning. Widgets and Watch complications are strong leverage."
        ),
        niche_seeds=[
            "budget app", "expense tracker", "savings goals",
            "investment tracker", "subscription tracker", "debt payoff",
            "net worth", "split bills",
        ],
        subreddits=[
            "personalfinance", "povertyfinance", "investing",
            "Frugal", "ynab", "leanfire",
        ],
        avoid="anything regulated as banking, crypto trading platforms",
        target_idea_count=3,
        min_score=60,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="budget-conscious adults 25–45, DIY personal-finance crowd",
        monetization_preference="subscription",
    ),
    "Travel & local": RunConfig(
        focus_prompt=(
            "iOS apps for travelers — trip itineraries, packing lists, offline "
            "maps, currency converter, language phrasebook, restaurant finder, "
            "transit. Offline-first is a strong positioning (no signal abroad). "
            "Camera + Translate API + Maps deep links are real leverage."
        ),
        niche_seeds=[
            "trip planner", "packing list", "offline map",
            "currency converter", "travel itinerary", "restaurant finder",
            "transit app", "phrasebook",
        ],
        subreddits=[
            "travel", "solotravel", "digitalnomad",
            "backpacking", "JapanTravel", "onebag",
        ],
        avoid="hotel booking apps competing with Booking / Airbnb",
        target_idea_count=3,
        min_score=58,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="frequent travelers, digital nomads, vacation planners",
        monetization_preference="one-time",
    ),
    "Food & cooking": RunConfig(
        focus_prompt=(
            "iOS apps for food planning and cooking: recipe organizers, meal "
            "planners, grocery-list builders, dietary trackers, kitchen timers. "
            "Live Activities for cook timers, Watch complications for grocery "
            "lists, widgets for 'what's for dinner' — all leverage."
        ),
        niche_seeds=[
            "recipe app", "meal planner", "grocery list",
            "dietary tracker", "cooking timer", "food diary",
            "kitchen scale", "pantry tracker",
        ],
        subreddits=[
            "MealPrepSunday", "Cooking", "EatCheapAndHealthy",
            "Veganism", "slowcooking", "AskCulinary",
        ],
        avoid="food-delivery aggregators, restaurant-ordering platforms",
        target_idea_count=3,
        min_score=58,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="home cooks, meal planners, dietary-conscious adults",
        monetization_preference="freemium",
    ),
    # ───── Platform-specialized picks ────────────────────────────────────
    "Apple Pencil & iPad-native": RunConfig(
        focus_prompt=(
            "Apps that lean hard into iPad hardware: Apple Pencil pressure & tilt, "
            "large screen, Stage Manager, Files app, external display. Creative "
            "power tools — sketching, note-taking, music production, design, "
            "writing. Premium pricing: one-time $15–50 or annual sub for pros."
        ),
        niche_seeds=[
            "ipad notes", "sketching app", "sheet music",
            "music production ipad", "design tool", "mind map",
            "ipad illustration", "journal ipad",
        ],
        subreddits=[
            "ipad", "iPadPro", "ApplePencil", "ProCreate",
            "illustration", "writing", "MusicProduction", "DigitalArt",
        ],
        avoid="phone-only apps, casual social apps",
        target_idea_count=3,
        min_score=60,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="creative pros, students, hobbyists with an iPad + Pencil",
        monetization_preference="one-time",
    ),
    "Camera · AR · on-device AI": RunConfig(
        focus_prompt=(
            "Camera-first iPhone apps. ARKit, Vision, Core ML, on-device LLMs. "
            "Turn the camera into a useful tool — scan, measure, identify, "
            "translate, augment. Privacy-friendly (on-device > cloud) is a "
            "selling point. Freemium with a hard paywall after a few uses."
        ),
        niche_seeds=[
            "document scanner", "plant identifier", "ar measure",
            "ar room scan", "calorie photo", "translate camera",
            "color picker", "object identifier",
        ],
        subreddits=[
            "iphone", "iOSProgramming", "augmentedreality",
            "MachineLearning", "photography", "AppHookup",
        ],
        avoid="generic photo filters, social photo sharing",
        target_idea_count=3,
        min_score=60,
        feasibility_filter=["solo-1mo", "solo-3mo"],
        audience_hint="utility-first iPhone users, prosumers",
        monetization_preference="freemium",
    ),
    "Widgets · Watch · Live Activities": RunConfig(
        focus_prompt=(
            "iOS apps whose primary value lives outside the main app — Home "
            "Screen widgets, Lock Screen widgets, Live Activities, Dynamic "
            "Island, Apple Watch complications. The core experience is a "
            "glance, not a session. Aesthetic, customizable, fast."
        ),
        niche_seeds=[
            "home screen widget", "lock screen widget", "apple watch app",
            "live activity", "dynamic island", "focus mode",
            "complication", "standby mode app",
        ],
        subreddits=[
            "iphone", "ios", "AppleWatch", "productivity",
            "AppHookup", "iOSthemes",
        ],
        avoid="apps where the widget is just a launcher",
        target_idea_count=4,
        min_score=58,
        feasibility_filter=["solo-1wk", "solo-1mo"],
        audience_hint="aesthetic-conscious iPhone users, Apple Watch owners",
        monetization_preference="freemium",
    ),
    "Indie dev tools (iOS-native)": RunConfig(
        focus_prompt=(
            "Tools developers and technical hobbyists wish existed natively on "
            "iPhone or iPad. Lean into iOS strengths: Shortcuts, Files, App "
            "Intents, Keychain, background processing, ssh / git clients. "
            "Power users will pay $20–50 one-time for a polished native tool."
        ),
        niche_seeds=[
            "regex tester", "json viewer", "api client mobile",
            "ssh client", "code snippet", "git mobile",
            "http inspector", "icon generator",
        ],
        subreddits=[
            "iOSProgramming", "swift", "indiehackers",
            "programming", "webdev", "apple", "SideProject",
        ],
        avoid="consumer-facing apps, generic productivity, fitness, casual games",
        target_idea_count=3,
        min_score=60,
        feasibility_filter=["solo-1wk", "solo-1mo"],
        audience_hint="developers, technical hobbyists, indie makers",
        monetization_preference="one-time",
    ),
}

PRESET_NAMES: list[str] = list(PRESETS.keys())
