/**
 * What tells that a card is really seen: the tab is visible and the card is
 * on the screen. The card of a received reflection records its reading only
 * then (`LinkupRefletCard`).
 *
 * The methods are those of an object, so the tests replace them with
 * `patchWithCleanup` instead of driving the visibility of the browser.
 */

/** Part of the card, or of the viewport for a card taller than it, that
 * must be on the screen. */
export const LINKUP_READ_RATIO = 0.5;

export const linkupReadWatch = {
    /** @returns {boolean} whether the tab is shown to the user */
    isPageVisible() {
        return document.visibilityState === "visible";
    },

    /**
     * Call `onChange(isOnScreen)` whenever the element enters or leaves the
     * screen. An element counts as on the screen when `LINKUP_READ_RATIO`
     * of it is shown, or when it fills that part of the viewport, so a card
     * taller than the screen is seen as well. Without
     * `IntersectionObserver`, the element counts as always on the screen.
     *
     * @param {HTMLElement} el
     * @param {(isOnScreen: boolean) => void} onChange
     * @returns {() => void} stops the watch
     */
    observe(el, onChange) {
        if (typeof IntersectionObserver === "undefined") {
            onChange(true);
            return () => {};
        }
        const observer = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    const rootHeight = entry.rootBounds?.height || Infinity;
                    onChange(
                        entry.isIntersecting &&
                            (entry.intersectionRatio >= LINKUP_READ_RATIO ||
                                entry.intersectionRect.height >= rootHeight * LINKUP_READ_RATIO)
                    );
                }
            },
            // Steps of a tenth: a card taller than the screen crosses no
            // ratio of its own while it fills the viewport.
            {threshold: Array.from({length: 11}, (_, index) => index / 10)}
        );
        observer.observe(el);
        return () => observer.disconnect();
    },
};
