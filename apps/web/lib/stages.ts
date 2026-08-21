type ProjectStageDefinition = {
  name: string;
  states: readonly string[];
  detail?: string;
  displayName?: string;
};

export const projectStages: readonly ProjectStageDefinition[] = [
  { name: "项目对齐", states: ["alignment"] },
  { name: "MRD", states: ["mrd"] },
  { name: "PRD", states: ["prd"] },
  { name: "方案确认", states: ["solution_confirmation"] },
  { name: "技术栈确认", states: ["tech_stack_confirmation"] },
  {
    name: "分阶段开发",
    displayName: "开发",
    states: ["development_backend", "development_frontend"],
    detail: "后端 → 前端",
  },
  { name: "MVP", states: ["mvp"] },
  { name: "内部验收", states: ["internal_acceptance"] },
  { name: "种子用户内测", states: ["seed_beta"] },
  { name: "BRD/商业模式确认", states: ["brd"] },
  { name: "发布/交接", states: ["release_handoff"] },
  { name: "数据与反馈", states: ["feedback"], detail: "→ 下一轮" },
];

export function projectStageIndex(state: string) {
  return projectStages.findIndex((stage) => stage.states.some((candidate) => candidate === state));
}

export function projectStageLabel(state: string) {
  const index = projectStageIndex(state);
  return index >= 0 ? projectStages[index].name : state;
}

export function projectInternalStageLabel(state: string) {
  if (state === "development_backend") return "后端开发";
  if (state === "development_frontend") return "前端开发";
  return projectStageLabel(state);
}
