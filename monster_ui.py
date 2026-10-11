"""Presentation-only weekly Monster hero. No picks, models, or database access."""

MONSTER_HERO_HTML = """
<style>
.monster-hero {
    position: relative;
    overflow: hidden;
    margin: 0 0 28px;
    padding: 26px;
    border: 2px solid #39ff88;
    border-radius: 22px;
    background: linear-gradient(145deg, #071c12, #101714 65%, #072516);
    box-shadow: 0 0 24px #39ff8833, inset 0 0 28px #39ff8810;
    color: #e8fff0;
}
.monster-hero * { box-sizing: border-box; }
.monster-eyebrow {
    margin: 0 0 8px;
    color: #71ffa8;
    font-size: 12px;
    letter-spacing: .18em;
    text-transform: uppercase;
}
.monster-hero h2 {
    margin: 0;
    color: #71ffa8;
    font-size: clamp(26px, 5vw, 42px);
    text-shadow: 0 0 16px #39ff8855;
}
.monster-intro {
    margin: 10px 0 22px;
    color: #bfd8c9;
    line-height: 1.6;
}
.monster-machine {
    display: grid;
    grid-template-columns: 1fr 150px 1fr;
    gap: 14px;
    padding: 16px;
    border: 1px solid #39ff8844;
    border-radius: 16px;
    background: #030b07;
}
.monster-reel {
    display: flex;
    min-height: 150px;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 14px;
    border: 1px solid #39ff8833;
    border-radius: 12px;
    background: linear-gradient(#0b2115, #07110b);
    text-align: center;
}
.monster-reel-label {
    color: #a2bfae;
    font-size: 11px;
    letter-spacing: .12em;
    text-transform: uppercase;
}
.monster-reel-value {
    margin: 10px 0;
    color: #71ffa8;
    font-size: 22px;
    font-weight: 700;
}
.monster-reel-note { color: #a2bfae; font-size: 12px; }
.monster-face {
    position: relative;
    width: 100px;
    height: 100px;
    border: 3px solid #71ffa8;
    border-radius: 50%;
    background: #102a1b;
    box-shadow: 0 0 22px #39ff8855;
    animation: monster-spin 8s linear infinite;
}
.monster-eyes {
    position: absolute;
    top: 17px;
    left: 0;
    right: 0;
    color: #71ffa8;
    font-size: 29px;
    font-weight: 800;
    letter-spacing: 9px;
    padding-left: 9px;
}
.monster-smile {
    position: absolute;
    bottom: 19px;
    left: 25px;
    width: 44px;
    height: 23px;
    border-bottom: 4px solid #71ffa8;
    border-radius: 0 0 40px 40px;
}
.monster-status {
    margin: 20px 0 8px;
    color: #e8fff0;
    font-size: 17px;
    font-weight: 700;
}
.monster-disclaimer {
    margin: 0;
    color: #a2bfae;
    font-size: 13px;
    line-height: 1.6;
}
@keyframes monster-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
@media (max-width: 600px) {
    .monster-hero { padding: 18px; }
    .monster-machine { grid-template-columns: 1fr; }
    .monster-reel { min-height: 110px; }
    .monster-center { grid-row: 1; min-height: 145px; }
}
@media (prefers-reduced-motion: reduce) {
    .monster-face { animation: none; }
}
</style>

<section class="monster-hero" aria-labelledby="monster-title">
    <p class="monster-eyebrow">Weekly showcase</p>
    <h2 id="monster-title">🎰 Weekly Monster</h2>
    <p class="monster-intro">
        Your weekly ticket showcase.
    </p>

    <div class="monster-machine">
        <div class="monster-reel">
            <span class="monster-reel-label">Ticket</span>
            <span class="monster-reel-value">Coming soon</span>
            <span class="monster-reel-note">No ticket available</span>
        </div>

        <div class="monster-reel monster-center">
            <div class="monster-face" aria-hidden="true">
                <span class="monster-eyes">&#36;&#36;</span>
                <span class="monster-smile"></span>
            </div>
        </div>

        <div class="monster-reel">
            <span class="monster-reel-label">Estimated return</span>
            <span class="monster-reel-value">—</span>
            <span class="monster-reel-note">Available when a ticket is published</span>
        </div>
    </div>

    <p class="monster-status">Waiting for a weekly ticket.</p>
    <p class="monster-disclaimer">
        Preview only. No ticket or return is available.
    </p>
</section>
"""


def add_monster_hero(template):
    """Insert once at the top of the dashboard's main content."""
    if 'id="monster-title"' in template:
        return template
    if template.count("<main>") != 1:
        raise ValueError("Expected exactly one dashboard main element")
    return template.replace("<main>", "<main>" + MONSTER_HERO_HTML, 1)
