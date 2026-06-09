# LIDOM Hitter Projection Grader - Version 2

This version is built for a hitter summary CSV that already includes the important columns.

## Expected columns

- playerFullName
- ForwVel
- ExitVel
- LaunchAng
- OPS vs FB95
- Contact%
- Hard Hit%
- Pull%

The app will auto-map those names when it sees them.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## What changed in Version 2

Removed raw pitch-level mapping fields:
- Pitch Velocity
- PitchCall
- Play Result / Result
- Pitch Type

Added direct metric fields:
- OPS vs FB95
- Contact
- Hard Hit
- Pull
