/** Inline mark so the glyph uses theme color with a truly transparent canvas (no img raster quirks). */
const D =
  "M830.035 682.864V341.136L512 52.2656L193.964 341.136V682.864L512 971.734L830.035 682.864ZM512 334.85L641.542 452.573V571.427L512 689.15L382.458 571.427V452.573L512 334.85ZM533.202 895.18V727.05L787.63 495.941V664.071L533.202 895.18ZM787.63 438.745L683.947 532.898V433.78L533.202 296.825V128.694L787.63 359.803V438.683V438.745ZM490.797 128.694V296.825L340.053 433.78V532.898L236.432 438.745V359.866L490.86 128.757L490.797 128.694ZM236.369 496.004L339.99 590.157L452.042 691.978L490.734 727.112V895.243L236.306 664.134V496.004H236.369Z";

type Props = {
  className?: string;
};

export default function Logomark({ className }: Props) {
  return (
    <svg
      className={className}
      viewBox="0 0 1024 1024"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
      focusable="false"
    >
      <path d={D} fill="currentColor" />
    </svg>
  );
}
