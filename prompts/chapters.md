# Chapters

Split the video into chapters using the timestamps given in the content.

## Rules
- `start` is in seconds and must be copied from or derived from the timestamps provided.
  Never invent a time that is outside the video.
- The first chapter must start at 0.
- At least 3 chapters, each at least 10 seconds long, in increasing order of `start`.
  If the video is too short for 3 chapters, return as many as fit.
- Titles: 2 to 6 words, descriptive, no numbering.

## JSON keys
```json
{
  "chapters": [
    {"start": 0, "title": "Intro and goal"},
    {"start": 95, "title": "Setting up the project"}
  ]
}
```
