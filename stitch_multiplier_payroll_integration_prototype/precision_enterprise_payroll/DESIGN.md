---
name: Precision Enterprise Payroll
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#45464d'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#76777d'
  outline-variant: '#c6c6cd'
  surface-tint: '#565e74'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#131b2e'
  on-primary-container: '#7c839b'
  inverse-primary: '#bec6e0'
  secondary: '#515f74'
  on-secondary: '#ffffff'
  secondary-container: '#d5e3fc'
  on-secondary-container: '#57657a'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#001d31'
  on-tertiary-container: '#188ace'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2fd'
  primary-fixed-dim: '#bec6e0'
  on-primary-fixed: '#131b2e'
  on-primary-fixed-variant: '#3f465c'
  secondary-fixed: '#d5e3fc'
  secondary-fixed-dim: '#b9c7df'
  on-secondary-fixed: '#0d1c2e'
  on-secondary-fixed-variant: '#3a485b'
  tertiary-fixed: '#cce5ff'
  tertiary-fixed-dim: '#93ccff'
  on-tertiary-fixed: '#001d31'
  on-tertiary-fixed-variant: '#004b73'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
  tabular-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0em
  tabular-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-sm: 0.5rem
  gutter-lg: 1.5rem
  margin: 1.5rem
  margin-sm: 1rem
  margin-lg: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system is engineered for mission-critical enterprise human resources, compensation planning, and payroll execution. It prioritizes clarity, informational density, and absolute operational trust over stylistic novelty.

### Aesthetic Foundation
- **Calm Utility & Precision**: The visual landscape operates like high-grade institutional accounting tools. Every element exists to clarify data states, audit trails, and execution workflows.
- **Restraint Over Expression**: No decorative illustrations, extraneous drop shadows, or loud marketing gradients. Contrast is measured to prevent fatigue over continuous 8-hour administrative sessions.
- **Embedded Architectural Alignment**: Modeled on high-reliability ERP interfaces (such as Workday or institutional ledger software), using a structural container framework governed by fine gridlines and subdued slate separators.

### User Persona & Mental Model
The primary users are payroll managers, human resources directors, and compliance officers handling high-consequence data batches (statutory deductions, direct deposits, tax filings, workforce reorganizations). The design communicates stability, deterministic behavior, and immediate visibility into exceptions and blockers.

## Colors

The system uses a neutral slate canvas where functional color is exclusively reserved for validation states, process flows, and system health indicators.

### Foundational Palette
- **Primary Canvas**: `#F8FAFC` (App background / base canvas)
- **Layer & Container Surface**: `#FFFFFF` (Card surfaces, data tables, sidebars)
- **Recessed Surface**: `#F1F5F9` (Table column headers, subtle striping, read-only control states)
- **Structural Border & Divider**: `#E2E8F0` (Default 1px line rules)
- **Active / Focused Border**: `#CBD5E1` (Interactive outline state)
- **Text Primary**: `#0F172A` (Headings, primary values, active data cells)
- **Text Secondary**: `#475569` (Form field labels, metadata, breadcrumb segments)
- **Text Muted / Placeholder**: `#64748B` (Input placeholders, inactive timestamps)

### Semantic & Status Tiers
Status values are subdued, utilizing desaturated pastel backdrops with dark, high-contrast foreground text to preserve visual calm in dense tables:
- **On-Track / Reconciled (Emerald)**: Background `#ECFDF5`, Border `#A7F3D0`, Text `#065F46`
- **Needs Confirmation / Pending Review (Amber)**: Background `#FFFBEB`, Border `#FDE68A`, Text `#92400E`
- **Blocking / Error / Deadline Risk (Rose)**: Background `#FFF1F2`, Border `#FECDD3`, Text `#9F1239`
- **Informational / Processing (Sky)**: Background `#F0F9FF`, Border `#BAE6FD`, Text `#075985`

## Typography

The type scale is compact, calibrated specifically for complex data entry and multi-column tabular layouts.

### Usage Standards
- **Font Family**: Inter, leveraging native tabular figures (`font-variant-numeric: tabular-nums`) across all numeric calculations, account IDs, currency sums, and date formats.
- **Headline Discipline**: Single-line headers are standard across panels and workspaces. Multi-line wrapping on page titles and table headers is avoided; text should truncate with tooltips if column bounds are exceeded.
- **Hierarchy Rules**: 
  - Section titles and main workspace headers use `headline-lg` (20px) or `headline-md` (16px).
  - All form controls and standard data cells render at `body-md` (13px) for balanced scanning and density.
  - Column headers, auxiliary captions, and badge labels use `label-sm` (11px) with medium weights.

## Layout & Spacing

A compact 4px grid governs all spatial parameters. Content architecture prioritizes dashboard density and high horizontal data span.

### Grid & Layout Structure
- **Global Frame**: Desktop-first layout featuring a fixed 240px navigation shell, a fixed sub-navigation or audit drawer where needed, and a fluid main data canvas (`min-width: 1024px`).
- **Data Workspaces**: Tables and field grids follow a 12-column responsive fluid grid with tight 16px (`gutter`) column separations to maximize table visibility on standard 1080p laptop displays.
- **Vertical Density**: Form rows adhere to a strict 36px line height budget. Standard grid rows sit at 40px base height, compact mode at 32px.
- **Margins & Edge Spacing**: Canvas wrapper padding is locked to `1.5rem` (`24px`). Internal panel padding operates on a compact `0.75rem` (`space-md`) to `1rem` (`space-lg`) scale.

## Elevation & Depth

This system avoids ambient shadows, blur mechanics, or decorative lighting. All depth is structural and flat, communicated through crisp low-contrast borders and tonal contrast.

### Surface Hierarchy
1. **Level 0 (Canvas Base)**: `#F8FAFC`. Houses the application shell, structural dividing gutters, and page headers.
2. **Level 1 (Card & Workspace Panels)**: `#FFFFFF`. Contained within a razor-sharp 1px border (`#E2E8F0`). Flat, zero shadow.
3. **Level 2 (Recessed & Sub-components)**: `#F1F5F9`. Table header rows, disabled entry zones, and subtle audit trails inset directly into Level 1 containers.
4. **Level 3 (Overlays & Modals)**: Floating dialogs, context action menus, and dropdown lists use `#FFFFFF` with a 1px `#CBD5E1` outline and a restrained structural shadow: `0px 4px 6px -1px rgba(15, 23, 42, 0.08), 0px 2px 4px -2px rgba(15, 23, 42, 0.04)`.

## Shapes

The design uses tight, restrained corner radiuses (`roundedness: 1`, corresponding to `4px` base border-radius) to support an architectural, tabular appearance.

### Geometry Parameters
- **Data Fields & Form Controls**: `4px` border-radius (`0.25rem`). Maintains vertical alignment with table grid lines and container borders.
- **Cards, Panels, and Sheets**: `6px` to `8px` max outer corner radius to prevent visual heaviness at container junctions.
- **Status Badges & Tokens**: `4px` border radius (`rounded-sm`). Fully rounded pill badges are explicitly prohibited to prevent casual, consumer-app styling.
- **Selection Controls**: Checkboxes feature a clean `3px` radius; radio targets are true circles (`50%`).

## Components

### Buttons
- **Primary Action**: Background `#0F172A`, text `#FFFFFF`, border `1px solid transparent`. Height: 32px (standard) or 28px (compact). Padding: 0 12px. Font: `label-md`. Hover: `#1E293B`.
- **Secondary Action**: Background `#FFFFFF`, text `#0F172A`, border `1px solid #E2E8F0`. Hover: `#F1F5F9`. Active: `#E2E8F0`.
- **Tertiary / Ghost**: Background transparent, text `#475569`, border none. Hover: `#F1F5F9`, text `#0F172A`.

### Data Tables & Grid Systems
- **Header Cells**: 32px height, background `#F1F5F9`, text `#475569`, font `label-sm`, uppercase or sentence-cased tracking, bottom border `1px solid #E2E8F0`.
- **Body Cells**: 40px standard height, background `#FFFFFF`, text `#0F172A`, font `body-md`, border-bottom `1px solid #F1F5F9`. Right-aligned for tabular currency and numeric figures.
- **Row States**: Hover state uses `#F8FAFC`. Selected row uses `#F0F9FF` with an active 2px `#0284C7` accent indicator on the leftmost edge.

### Status Badges
- **Dimensions**: Fixed 20px height, inline-flex, align-items center, padding `0 6px`, radius `4px`.
- **Typography**: `label-sm`, medium weight (500), mono or tabular numerals if showing quantities.
- **Variants**:
  - *Reconciled / Matched*: `#ECFDF5` background, `#A7F3D0` 1px border, `#065F46` label.
  - *Needs Review / Warning*: `#FFFBEB` background, `#FDE68A` 1px border, `#92400E` label.
  - *Blocked / Escalated*: `#FFF1F2` background, `#FECDD3` 1px border, `#9F1239` label.
  - *Neutral / Draft*: `#F1F5F9` background, `#E2E8F0` 1px border, `#475569` label.

### Input Fields & Controls
- **Text Inputs**: Height 32px. Background `#FFFFFF`, border `1px solid #E2E8F0`, padding `0 8px`, typography `body-md`. Focus state uses border `1px solid #0F172A` with an ambient focus ring `box-shadow: 0 0 0 1px #0F172A`.
- **Checkboxes**: 16px × 16px square, radius `3px`, border `1px solid #CBD5E1`. Checked state: `#0F172A` fill with white checkmark icon.

### Cards & Grouping Containers
- **Border**: Single continuous `1px solid #E2E8F0`.
- **Background**: `#FFFFFF`.
- **Header**: Single-line 44px height container, border-bottom `1px solid #E2E8F0`, padding `0 16px`. Title uses `headline-sm` with optional right-aligned action buttons or audit time-stamps.