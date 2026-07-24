export default function ProgressRing({ percent, size = 72, strokeWidth = 5, children }) {
  const r = (size - strokeWidth) / 2
  const circ = 2 * Math.PI * r
  const offset = circ - (Math.min(percent, 100) / 100) * circ
  return (
    <div className="d-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle className="d-ring-bg" cx={size / 2} cy={size / 2} r={r} strokeWidth={strokeWidth} />
        <circle className="d-ring-fill" cx={size / 2} cy={size / 2} r={r} strokeWidth={strokeWidth}
          strokeDasharray={circ} strokeDashoffset={offset} />
      </svg>
      <div className="d-ring-text">
        {children}
      </div>
    </div>
  )
}
