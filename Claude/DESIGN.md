# Lineal Design System: Smart Urban Infrastructure
**Project:** Planeación Urbana Inteligente · Track IBM  
**Director’s Vision:** High-End Technical Precision with Enterprise Sophistication
**Aesthetic Direction:** Refined Minimalist Editorial (The "Urban Nexus")

---

### 1. Overview & Creative North Star: "The Urban Nexus"
The design system for **Lineal** is centered on the concept of the **"Urban Nexus."** It represents the point where complex municipal data meets actionable private investment. The interface is not just a dashboard; it is a precision instrument designed to feel like a high-end architectural tool.

This system rejects generic SaaS aesthetics. Instead, it utilizes **tonal elevation, premium glassmorphism, and high-contrast numerical scales** to convey authority and statistical depth.

---

### 2. Color Palette: Structural & Atmospheric
The palette is derived from IBM's enterprise DNA—utilizing deep, intellectual blues and a sophisticated array of functional greys.

*   **Primary / Action:** `#002D9C` (IBM Blue) - Used for primary CTAs like "Generate Optimized Plan."
*   **Surface (Base Canvas):** `#F4F7FB` - A cool, atmospheric grey-blue for the main background.
*   **Surface Layer (Cards/Panels):** `#FFFFFF` - Clean white surfaces to provide maximum contrast for data.
*   **Secondary Accent (Construction/ROI):** `#005D5D` (Teal) - Used for positive metrics and infrastructure growth.
*   **Risk/Alert (Climate/Constraints):** `#DA1E28` (Red) - Used for flooding risks and regulatory blockers.
*   **Text (Primary):** `#161616` - Near-black for maximum readability.
*   **Text (Metadata):** `#525252` - Mid-grey for secondary information and labels.

---

### 3. Layout: The Three-Pane Framework
The interface is divided into three distinct functional zones to streamline the user flow.

1.  **Exploration Pane (Left Sidebar):**
    *   **Focus:** Input and Filtering.
    *   **Style:** Minimalist icons with high-density controls (sliders, select menus).
    *   **Visual Mark:** Transparent background with subtle vertical navigation markers.
2.  **Visualization Pane (Center Map):**
    *   **Focus:** Spatial Context.
    *   **Engine:** **MapLibre GL JS** with vector tiles.
    *   **Overlays:** High-fidelity polygons with distinct fills for "Target Zones." Floating legends with backdrop-blur (`blur-xl`).
3.  **Synthesis Pane (Right Sidebar):**
    *   **Focus:** Analytical Output (The "Lineal" Analysis).
    *   **Style:** A vertical scroll of high-contrast cards.
    *   **Signature Element:** Huge numerical displays for Impact/ROI (`font-bold`, `text-3xl`).

---

### 5. Asset Registry & Usage
The following assets from `/LINEAL-IBM/Assets/1x/` should be utilized to maintain brand consistency:

*   **Logotype:**
    *   `LogoConTrack.png`: Main logo for the header (Left Sidebar).
    *   `LogoSinCalle.png`: Minimalist version for footer or secondary navigation.
    *   `l.png`, `i.png`, `n.png`, `e.png`, `a.png`, `l.png`: Individual letter assets for creative loading sequences or staggered "reveal" animations.
*   **Visual Atmosphere:**
    *   `Decorativo.png`: Used as a low-opacity background texture for the "Synthesis Pane" to add depth.
    *   `Plano.png`: Subtle blueprint overlay for empty states or "Loading AI Proposal" views.
*   **Color Guidance:**
    *   `PaletaDeColores.png`: Visual reference for all manual CSS variable implementation.

---

### 6. Technical Performance Guidelines (React Best Practices)
To ensure the "streamline" promise, the frontend must remain highly performant despite the heavy geospatial data.

*   **Eliminating Waterfalls (async-parallel):**
    *   Fetch all agent recommendations and the SIIMP map layers in parallel using `Promise.all()` to prevent UI blocking.
*   **Bundle Optimization (bundle-dynamic-imports):**
    *   Load the **MapLibre GL JS** engine dynamically using `next/dynamic` or lazy loading to ensure the initial shell of the app loads in <1s.
*   **Re-render Optimization (rerender-memo):**
    *   Memoize the **Right Sidebar Cards** as they contain static analytical data. Do not re-render them when the user interacts with the map unless the data itself changes.
*   **Rendering Performance (rendering-content-visibility):**
    *   Use `content-visibility: auto` for the ranked opportunities list if it becomes long, ensuring the browser only paints visible projects.
*   **Motion (Motion Library):**
    *   Implement **Staggered Entry** for the analytical cards on the right. Each card should drift upwards with a `0.1s` delay from its predecessor to create a "thoughtful" reveal.

---

### 7. Component Styles (Refined)

#### AI Reasoning & Feasibility Card
This is the "brain" of the proposal. 
*   **Visual Marker:** A thick 4px vertical bar (`#002D9C`) on the left.
*   **Background:** A very subtle light blue tint (`#E0E8F5`).
*   **Typography:** Small, uppercase headers for section titles; clear, legible body text for agent justifications.

#### Impact Metrics
*   **Layout:** 2x2 grid of cards.
*   **Visuals:** Large text indicators for \% changes.
*   **Icons:** Micro-icons (rain for retention, density icon, budget symbol) to reinforce data at a glance.

#### Map Controls
*   **Style:** Floating vertical stack in the bottom right.
*   **Look:** White circular buttons with thin grey borders and dark grey icons.

---

### 8. Typography: Precision Editorial
*   **Headlines (Sans-Serif):** IBM Plex Sans or Inter. Used for a clean, technical look.
*   **Numerical Data:** Monospace or high-contrast Sans-Serif (e.g., Space Grotesk) to highlight the quantitative nature of the tool.
*   **Labels:** All-caps, tracked-out (+0.05em) for metadata categories (e.g., "EST. BUDGET", "DENSITY IMPACT").

---

### 9. Design Constraints (The "Do's and Don'ts")

*   **Do** use tonal shifts instead of heavy borders to separate sections.
*   **Do** use 8px rounded corners (`rounded-lg`) for cards to maintain a structured, professional feel.
*   **Do** emphasize "AI Synthesized" content with its own background treatment (Surface Accent) and a glassmorphism blur effect (`backdrop-blur-xl`).
*   **Don't** use generic AI-slop fonts (Arial, Roboto). Stick to **IBM Plex Sans** for navigation and **Space Grotesk** for numerical precision.
*   **Don't** use standard shadows. Use "Ambient Elevation"—very subtle, large-blur shadows with low opacity (3-5%).