/**
 * 复刻 Python `round()` 的银行家舍入（round-half-to-even），
 * 保证金额/均价等统计数字与 Python 版一致。
 *
 * Python `round(2.5) == 2`，`round(3.5) == 4`；JS `Math.round` 是四舍五入（half-up），
 * 在 .5 边界上会差 1，故必须自行实现。
 */
export function pyRound(value: number, ndigits = 0): number {
  if (!Number.isFinite(value)) return value;
  if (ndigits === 0) return roundHalfEven(value);
  const factor = 10 ** ndigits;
  // 先放大再做 half-even，尽量避免浮点误差放大
  return roundHalfEven(value * factor) / factor;
}

function roundHalfEven(x: number): number {
  const floor = Math.floor(x);
  const diff = x - floor;
  if (diff > 0.5) return floor + 1;
  if (diff < 0.5) return floor;
  // diff === 0.5（含浮点近似）：偶数不变，奇数进一
  return floor % 2 === 0 ? floor : floor + 1;
}
