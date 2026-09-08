import { pestTargets } from '../domain/catalog';

function literal(value: string) { return `'${value.replaceAll("'", "''")}'`; }
function matches(column: string, alias: string) {
  const token = literal(alias.toUpperCase());
  // Korean legacy labels include compounds such as 응애의심. English aliases use word boundaries.
  if (/[가-힣]/.test(alias)) return `instr(${column}, ${literal(alias)}) > 0`;
  return `instr('_' || replace(replace(upper(${column}), '-', '_'), ' ', '_') || '_', '_' || ${token} || '_') > 0`;
}

export function pestCodeSql(prediction = 'fp', run = 'ir') {
  const targets = pestTargets.filter((target) => target.code !== 'OTHER');
  // A class label takes precedence over a multi-task run's name.
  const cases = [`${prediction}.class_label`, `${run}.task`].flatMap((column) => targets.map((target) =>
    `WHEN (${target.aliases.map((alias) => matches(column, alias)).join(' OR ')}) THEN ${literal(target.code)}`));
  return `(CASE ${cases.join(' ')}
    WHEN upper(${run}.task) GLOB 'PEST_*' OR upper(${run}.task) GLOB 'DISEASE_*'
      OR upper(${prediction}.class_label) GLOB 'PEST_*' OR upper(${prediction}.class_label) GLOB 'DISEASE_*'
    THEN 'OTHER' ELSE NULL END)`;
}
