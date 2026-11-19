# Aldervale — Brookhollow Farm

A first-person cozy farming game in Three.js (TypeScript, Vite). The Crown gives you the wild old
homestead below Aldervale Castle: clear the land, raise a mill, keep hens, bake for the castle,
and by harvest-tide supply the first Harvest Feast in a generation.

## Play

```bash
npm install
npm run dev
```

Then open the address Vite prints. Progress saves in the browser; **New farm** on the title screen
starts over.

| Keys | |
|---|---|
| W A S D | walk · Shift run · Space jump |
| 1 – 6 | hoe, seed bag, watering can, basket, axe, pick (scroll wheel cycles) |
| Q | switch seed |
| Click | use the tool on what you look at (hold to work along a row) |
| E | talk, open, pack, build, or do the sensible thing |
| J | journal · M music · Esc pause |

## The year at Brookhollow

1. **The Steward Arrives** — meet Pip, harvest, till, plant, water, and send the first crate up the hill.
2. **Room to Grow** — Old Tom's axe and pick: clear the overgrown furrows, chop timber, trade with Wren.
3. **The Mill on the Rise** — raise the windmill and grind flour in its hopper.
4. **Hens and Hearth** — a hen house and a bakehouse oven; bake for the princess.
5. **The Harvest Feast** — three crates for the King's tables, and fireworks over the castle.

After the feast the farm carries on with standing orders from the castle.

## Making of

- All models are built in Blender from Python scripts in `tools/blender/` and exported to
  `public/models/*.glb`; the game swaps in its own PBR materials by name.
- Textures are generated procedurally (`tools/textures/`); sound is synthesised with WebAudio.
- `npm run build` type-checks and builds to `dist/`; a GitHub Actions workflow deploys `main` to Pages.
