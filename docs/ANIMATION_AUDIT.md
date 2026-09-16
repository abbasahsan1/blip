# Animation and Performance Audit

This document tracks all animations and performance optimizations applied to the Blipp mobile frontend. 

The goal of these modifications is to strictly enforce the "Animation Must Have a Purpose" rule, eliminate expensive permanent loops, and create a smooth, native-feeling vertical scrolling experience without forcing heavy React component re-renders.

## Eliminated Animations

1. **AudioReel Bouncing Heart:**
   - **Reason**: Violated the "No Spring Everything" rule. The massive heart scaling distracted from the content and felt like an event rather than simple feedback.
   - **Replacement**: Simple active color state and standard opacity press feedback (`<Pressable>`).
2. **AudioReel Scrolling Track Name:**
   - **Reason**: Violated the "No Permanent Decorative Loops" rule. It was powered by a continuous `Animated.loop` that re-rendered even when the user wasn't focused on the text.
   - **Replacement**: Truncated text (`numberOfLines={1}`) using a clean ellipses.
3. **AudioReel EQ Visualizer Bars:**
   - **Reason**: Fake visualizers create unnecessary UI noise and distract from the actual audio.
   - **Replacement**: Clean Play/Pause static icon with immediate state feedback.

## Performance Enhancements

1. **Audio Progress Throttling (`useAudioPlayer.ts`)**
   - **Issue**: `useAudioPlayer` previously used `useState` for the 0-1 playback `progress` fraction. Since the HTML5 Audio `timeupdate` event fires ~4-10 times per second, this was causing the entire `AudioReel` component to undergo expensive React re-renders up to 10 times a second for *each* playing component.
   - **Fix**: Replaced the `progress` state with a native `Animated.Value` that is manipulated directly via `progressAnim.setValue(frac)`. The scrubber inside `AudioReel.tsx` is now an `Animated.View` that interpolates the width directly on the native UI thread, bypassing React's render lifecycle entirely for playback ticks.
   - **State Throttling**: The `positionSeconds` and `durationSeconds` are still tracked in `useState`, but their setters are now throttled to only fire when their integer (whole seconds) values change, limiting re-renders to a maximum of 1 per second.

2. **Scroll Conflict Resolution (`index.tsx`)**
   - **Issue**: The main Feed `FlatList` possessed conflicting scroll directives: `pagingEnabled={true}` combined with `snapToInterval={feedHeight}`, `snapToAlignment="start"`, and `decelerationRate="fast"`. This conflict often causes double-snapping or stuttering because the OS-level pagination mechanism is fighting the custom JavaScript snap calculations.
   - **Fix**: Removed all manual snap properties. The feed now relies entirely on `pagingEnabled={true}` for buttery-smooth native screen-by-screen snapping.

## Next Steps / Verification

- Check for any other hooks or state updates that run faster than 1/second.
- Verify that opening/closing the Share modal doesn't cause unnecessary parent re-renders.
