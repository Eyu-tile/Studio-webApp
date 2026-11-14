# Brief: describe Spin360 clips from contact sheets

You are mapping the Spin360 footage library so an editor can pick b-roll and build UGC ads from a script without
opening the files. Work only from what you SEE on the sheets (and the transcript given for talking heads).
Never invent what you did not see. If unsure, say "unclear".

## The product (to recognise it)
Spin360 = luxury pedestal fan: round head with a clear/ribbed 360° cage of horizontal slats, a thin **gold halo ring**
under the top cover, a **blue LED ring** on the pole, a round black **digital display** on the pole (shows e.g. F3/F6),
round base. Colourways: **black** (black sparkle) and **white** (white pearl). Real units stand tall (long pole).
A scent/diffuser tray holds scent pads. Anything else (tower fans, box fans, ceiling fans, desk fans, AC units) is an
**other fan** = problem/before shot. Other brands' logos = flag.

## Brand look (for brand_fit)
Luxury. Quiet. Refreshing. Ideal: sheer curtains moving in a breeze, open window/door, sea/sky/lake/trees view, modern
airy light decor, sunlit. Low fit: cluttered, dark, messy, harsh light.

## Reading a sheet
Header: filename | duration | folder | id. Each tile is one frame, left→right, top→bottom, with its time in seconds.
"CUT" = a shot change just before that frame. A clip may have several sheets (_1, _2 ...): read all of them.

## Output: one JSON object per clip, in a JSON array, written to the output file you are given
{
 "id": "<full id>",
 "kind": "ugc_broll | ugc_talking_head | ai_generated | stock | product_only | graphic_text | mixed",
 "summary": "one plain sentence of what the clip is",
 "people": [{"who": "woman, 30s, long brown hair", "wardrobe": "pink dress", "role": "creator|actor|child|senior|hand only"}],
 "product": {"visible": "none|glimpse|partial|full|hero", "colourway": "black|white|both|none|unclear",
             "on": true|false|null, "details_seen": ["display F6","blue ring","gold halo","cage","scent tray","base","box/packaging"],
             "other_fans": ["black tower fan"], "other_brands": []},
 "setting": {"room": "bedroom|living room|kitchen|office|patio|nursery|outdoors|studio|other", "time": "day|night|evening|unclear",
             "light": "bright natural|warm lamp|dim|mixed", "view": "lake|sea|trees|city|none|unclear",
             "curtains_moving": true|false, "decor": "luxe|clean ordinary|cluttered"},
 "shots": [{"start": 0.0, "end": 3.2, "camera": "static|handheld|pan|tilt|push in|pull out|orbit|POV|selfie|gimbal",
            "framing": "wide|medium|close|macro|extreme close", "action": "what happens, concretely",
            "on_screen_text": "", "audio_hint": ""}],
 "best": {"start": 0.0, "end": 3.0, "why": "..."},
 "beats": ["hot_sleeper_problem","sweaty_discomfort","old_fan_annoyance","noise_problem","unboxing","assembly","turning_on",
           "control_display","airflow_demo_hand","airflow_demo_hair","airflow_demo_curtain_or_ribbon","quiet_demo","sleeping_comfort",
           "waking_refreshed","scent_tray","scent_reaction","room_aesthetic","product_hero","lifestyle_reading_relaxing",
           "family_kids","pets","outdoor_patio","before_after","reaction_face","cta_point","talking_to_camera"],
 "hook_potential": {"score": 0-3, "why": "..."},
 "brand_fit": {"score": 0-3, "why": "..."},
 "quality": {"score": 0-3, "issues": ["shaky","blurry","dark","overexposed","baked-in text","AI artefacts","watermark","vertical crop risk"]},
 "status": "OK|CAUTION|BANNED", "status_why": "",
 "tags": ["free words an editor would search: e.g. 'woman fans face with hand', 'kid asleep', 'ribbons fluttering'"]
}
For talking heads (a transcript is given) also add:
 "takes": [{"start": 9.0, "line": "first words of the line…", "delivery": "clean|stumble|restart|laugh|cut off",
            "energy": 0-3, "framing": "close|medium", "keep": true|false}],
 "best_takes": ["start times of the best take of each distinct line"],
 "speaker": {"look": "...", "setting": "...", "props": "..."}

Rules: times in seconds from the tile labels (shot boundaries at CUT marks; otherwise at visible changes). beats only
from the list (choose all that apply). status BANNED only for: another brand's logo prominent, nudity/unsafe, unusable
(black/corrupt). CAUTION for: other fan shown (problem shot only), AI artefacts, heavy baked-in text, very shaky/blurry.
Keep each field short and concrete. Valid JSON only.
