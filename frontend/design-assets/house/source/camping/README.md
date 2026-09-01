# Kikki Camping — separated animation assets

This folder contains the current camping-background layers as separate transparent PNGs, plus editable position/motion metadata.

## Files

- `assets/background/background_static.png` — fixed background plate
- `assets/scene/tent.png` — tent
- `assets/scene/light_post.png` — wooden light pole
- `assets/scene/tree_trunk.png` — fixed tree trunk/branches
- `assets/scene/tree_canopy.png` — moving leaf canopy
- `assets/scene/light_wire_fixed.png` — fixed wire + fixed hanging sockets
- `assets/clouds/cloud_01~03.png` — independent cloud pieces
- `assets/bulbs/bulb_01~10.png` — independent bulb bodies; their suspension pivots are stored in `scene-config.json`
- `assets/flowers/flower_*.png` — each visible flower is a separate PNG
- `assets/foliage/foliage_*.png` — smaller filler grass / flower clumps
- `assets/masters/*` — larger source sprites for future resizing/reuse
- `scene-config.json` — x/y, z-index, pivot, duration, angle/distance for every asset
- `preview.html` + `styles.css` — simple editable preview

## Coordinate system

The reference scene is **941 × 1672 px**.

`scene-config.json` uses absolute pixels from the top-left.

For a responsive implementation, scale positions by:

```js
const scaleX = renderedWidth / 941;
const scaleY = renderedHeight / 1672;
```

For the same aspect ratio, one scale value is enough.

## Editing motion

Each moving layer has a `motion` object in `scene-config.json`.

Examples:

```json
{
  "type": "sway",
  "durationSec": 3.8,
  "angleDeg": 1.5
}
```

```json
{
  "type": "driftX",
  "durationSec": 42,
  "distancePx": 16
}
```

For flowers and bulbs, use the supplied `pivotX` / `pivotY` as the transform origin. This keeps the flower root or bulb suspension point fixed while the visible part moves.

## Recommended implementation rule

Do not animate the whole flowerbed image. Animate each `flower_*.png` and `foliage_*.png` separately.  
Do not animate the whole string-light image. Keep `light_wire_fixed.png` still and animate only `bulb_*.png`.

That is what prevents the pixel boundary from tearing or the flower shape from collapsing.
