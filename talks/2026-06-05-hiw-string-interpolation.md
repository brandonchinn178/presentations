---
marp: true
theme: gaia
paginate: true
---

<!-- _class: lead -->

# GHC String Interpolation
##### _[GHC proposal #570](https://github.com/ghc-proposals/ghc-proposals/pull/570)_

Haskell Implementors' Workshop 2026
[@brandonchinn178](https://github.com/brandonchinn178)

---

## Schedule

- 5 min: Demo
- 15 min: Overview of feature
- 15 min: Reflections on process
- 10 min: Questions + Discussion

<!--
To start off, who here has been following the proposal?

Let me emphasize that the proposal is still evolving. I'm presenting the latest version of the proposal, but details may change in the final feature.
-->

---

## What is string interpolation?

```py
f"Expected: {x + y}, got: {result}"         # Python
```

```rust
format!("Expected: {sum}, got: {result}")  // Rust
```

```js
`Expected: ${x + y}, got: ${result}`       // Javascript/Typescript
```

```scala
s"Expected: ${x + y}, got: ${result}"      // Scala
```

<!--
String interpolation allows ergonomically building strings by inlining expressions directly in the string. It's available in many popular languages like Python, Rust, Javascript/Typescript, and Scala. Anecdotally, a lot of people coming to Haskell from these other languages ask how to do it / why Haskell doesn't have it, and it's one thing I personally miss a lot when writing Haskell.

I originally opened this proposal in Jan 2023. After lots of discussion and evolution, it should be in the final stages of review now, and will hopefully be available in GHC 10.2.
-->

---

<!-- _class: lead -->
## Demo

<!--
In ghc-string-interpolation-sandbox:
  - cabal run demo
  - cabal bench ./bench
-->

---

<!-- _class: lead -->
## Overview of feature

---

## Overview of feature
### `Interpolate` class

```hs
class Interpolate a where
  interpolate :: (IsString s, Monoid s) => a -> s
instance Interpolate String where
  interpolate = fromString
instance Interpolate Int where
  interpolate = fromString . show

instance Interpolate SrcLoc where
  interpolate SrcLoc{..} =
    interpolate file <> fromString ":" <>
    interpolate line <> fromString ":" <>
    interpolate col
```

<!--
First, we introduce the `Interpolate` class. One major advantage of string interpolation is the ability to automatically convert values to string within an interpolation.

Primitive values like `Int` should convert to `String`, then lifted with `fromString`. But most user-defined types should only need to delegate to other `Interpolate` instances, like `SrcLoc` here. You could implement `SrcLoc` here by converting to String with `fromString`, but keeping everything as `s` avoids roundtripping via String in some cases.
-->

---

## Overview of feature
### Desugaring

```hs
-- Input
s"Expected: ${x + y}, got: ${result}"

-- Desugared output
interpolateFinalize $
  interpolateRaw "Expected: " `interpolateAppend`
  interpolateValue (x + y)    `interpolateAppend`
  interpolateRaw ", got: "    `interpolateAppend`
  interpolateValue result     `interpolateAppend`
  interpolateEmpty
```

<!--
This is the final desugaring, but let's break it down in pieces.
-->

---

## Overview of feature
### Desugaring (step 1/3)

```hs
-- Input
s"Expected: ${x + y}, got: ${result}"

-- Desugared output; add fromString if -XOverloadedStrings
"Expected: "        <>
interpolate (x + y) <>
", got: "           <>
interpolate result
```

<!--
At its core, string interpolation simply calls `interpolate` on every value and concatenates them all together.

For simple examples like this, this should already be pretty performant. `mappend` is right-associative, so it should be linear performance. But what if `interpolate` does more concatenations? Let's use `ShowS` to be safe.
-->

---

## Overview of feature
### Desugaring (step 2/3)

```hs
-- Input
s"Expected: ${x + y}, got: ${result}"

-- Desugared output; add fromString if -XOverloadedStrings
buildString $
  fromString "Expected: " <>
  interpolate (x + y)     <>
  fromString ", got: "    <>
  interpolate result

-- Not pictured: IsString/Semigroup/Monoid instances
newtype StringBuilder = StringBuilder (String -> String)
buildString (StringBuilder f) = f ""
```

<!--
This uses the `ShowS` technique to avoid O(n^2) performance when `interpolate` includes additional concatenations.

Great; at this point, we're at a decent implementation for `String`.
-->

---

## Overview of feature
### Scorecard so far

* ✅ Decent performance for `String`
* ✅ Basic support for `-XOverloadedStrings`
* ⛔️ Not performant for `-XOverloadedStrings`
* ⛔️ No support for custom interpolators (e.g. HTML)

<!--
<Walk through each bullet>

To solve these last issues, we can turn to `-XQualifiedStrings`.
-->

---

## Overview of feature
### Slight detour: `-XQualifiedStrings`

- Coming out in GHC 10.0
- Adds `M."hello world"` syntax
  - Desugars to `M.fromString "hello world"`
- Like `-XQualifiedDo`, the only requirement is that it typechecks

<!--
How does this help us? Going back to where we left off:
-->

---

## Overview of feature
### Desugaring (step 2/3) (reminder)

```hs
-- Input
s"Expected: ${x + y}, got: ${result}"

-- Desugared output; add fromString if -XOverloadedStrings
buildString $
  fromString "Expected: " <>
  interpolate (x + y)     <>
  fromString ", got: "    <>
  interpolate result
```

<!--
This desugaring involves five points of customization: buildString, fromString, interpolate, and append/empty. To get to the final desugaring, we decouple the desugared function calls from the implementation.
-->

---

## Overview of feature
### Desugaring (step 3/3)

```hs
s"Expected: ${x + y}, got: ${result}"  -- Input

interpolateFinalize $          -- Desugared output
  interpolateRaw "Expected: " `interpolateAppend`
  interpolateValue (x + y)    `interpolateAppend`
  interpolateRaw ", got: "    `interpolateAppend`
  interpolateValue result     `interpolateAppend`
  interpolateEmpty

interpolateRaw      = fromString  :: String -> StringBuilder
interpolateValue    = interpolate :: Interpolate a => a -> StringBuilder
interpolateAppend   = mappend     :: StringBuilder -> StringBuilder -> StringBuilder
interpolateEmpty    = mempty      :: StringBuilder
interpolateFinalize = buildString :: String -> StringBuilder
```

<!--
Now, we can define the definitions at the bottom in some internal GHC module and desugar the interpolation this way. And now we have 5 functions that can be hooked into with QualifiedStrings (e.g. `M.interpolateRaw`, etc.)

You might be wondering why we don't keep fromString/mappend/etc. as the overloadable names with QualifiedStrings. If a module wants to be used with qualified strings and also export other names, these are common names that could conflict with other exports. This also clearly identifies the string interpolation functions separate from the rest of the API.

You might also be wondering why we should provide interpolateRaw/interpolateAppend/interpolateEmpty; we could instead always desugar to IsString/Monoid operations. But that restricts the ability for custom interpolators to those interfaces. For example, it would preclude type-changing appends like building a heterogenous list.
-->

---

## Overview of feature
### Built-in interpolator: `Basic`

```hs
module Data.String.Interpolate.Basic.Experimental where
(interpolateValue, interpolateFinalize) = (id, id)
-- Re-export interpolate{Raw,Append,Empty} from default interpolator
```

```hs
import Data.String.Interpolate.Basic.Experimental qualified as B
import Data.Text.Lazy.Builder qualified as B
import Data.Text.Lazy.Builder.Int qualified as B
main = do
  let name = "Alice"; age = 30 :: Int
  log B.s"Name: ${B.fromText name}, age: ${B.decimal age}"

log :: B.Builder -> IO ()
```

<!--
As part of the feature, we will also be shipping some interpolators out of the box in the `ghc-experimental` library. One useful interpolator is `Basic`, which does not do any implicit conversions or finalization. This is useful for cases like Text.Builder, where roundtripping via String using the built-in Interpolate class massively degrades performance, and it's reasonable to explicitly convert.
-->

---

## Overview of feature
### Final scorecard

- ✅ Decent performance for `String`
- ✅ Basic support for `-XOverloadedStrings`
- ✅ String-like types can provide performant interpolators with `-XQualifiedStrings`
- ✅ Support for custom interpolators with `-XQualifiedStrings`

---

<!-- _class: lead -->
## Reflections on process

---

## Reflections on process
### Why is it taking so long?

- 3 years (and counting!)
- 635 comments
- 1 survey
- Many major redesigns

---

## Reflections on process
### Reasons specific to string interpolation

* Low barrier to entry
* So much bikeshedding

<!--
Low barrier: String interpolation is a pretty unique feature in that even newcomers are familiar with it from other languages, so everyone has opinions, whether they're new to Haskell or have been around.

Bikeshedding: String interpolation also involves so many decisions: delimiter for quotes, delimiter to interpolate, whether to automatically convert or not, how performant it needs to be. It's hard to think of another proposal with this many orthogonal decisions that need to be made at once.

String interpolation in general is a large design space, so I think this particular proposal has unique challenges that probably won't be a common occurrence in other proposals.
-->

---

## Reflections on process
### Reasons specific to Haskell

- String vs Text
  * Choose 2: Ergonomic, performant, conceptually simple
  * Default interpolator: Simple, ergonomic, somewhat performant
  * Qualified interpolator: Simple, somewhat ergonomic, mostly performant

<!--
However, Haskell also has specific challenges that other languages don't face. The biggest one is having two utf-8 string types, where the more performant one is not in the stdlib. This forces us to make a trade-off between ergonomics, performance, and simplicity. The current design is relatively simple, with the default interpolator being ergonomic and somewhat performant, and qualified interpolators being somewhat ergonomic and mostly performant.

There's a lot of disagreement on the weighting of these priorities, which drags out the discussion.
-->

---

## Reflections on process
### Non-technical

* Theoretical purity vs practicality
* Github interface issues
  * [Rust workaround for viewing Github comments](https://triagebot.infra.rust-lang.org/gh-comments/rust-lang/rfcs/pull/3905)

<!--
Lastly, there's the non-technical aspects of the proposal. Let's be honest; we Haskellers love our theoretical purity, and this feature is completely driven by ergonomics and practicality. I'll give the community credit; I think overall, the community has engaged with the proposal well and in good faith. But there has been a non-zero number of people who feel strongly about 'Avoid "success at all costs"' and see this as unacceptable cost, which has added friction to the process. I do think some pushback is healthy, but I would challenge the community to keep this in mind and continue making sure pushback is in good faith.

The Github interface itself also made conversation a bit challenging. If Github hides a comment behind "Load more", you have to keep clicking "Load more" until you get to the end of the hidden history, which takes a long time for 627 comments. Also, if people make top-level comments, it's hard to respond to individual comments, especially if 5 top-level comments were added overnight. I don't have a good solution for this, and maybe this particular proposal is uniquely controversial such that this isn't a common problem, but I thought it would be worthwhile bringing up.
-->

---

<!-- _class: lead -->
## Discussion
