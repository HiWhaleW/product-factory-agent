import { describe, expect, it } from "vitest";

import {
  projectInternalStageLabel,
  projectStageIndex,
  projectStageLabel,
  projectStages,
} from "../lib/stages";

describe("frozen project stages", () => {
  it("keeps the 12 visible stages in their frozen order", () => {
    expect(projectStages.map((stage) => stage.name)).toEqual([
      "项目对齐",
      "MRD",
      "PRD",
      "方案确认",
      "技术栈确认",
      "分阶段开发",
      "MVP",
      "内部验收",
      "种子用户内测",
      "BRD/商业模式确认",
      "发布/交接",
      "数据与反馈",
    ]);
  });

  it("projects backend and frontend development into one visible stage", () => {
    expect(projectStageIndex("development_backend")).toBe(5);
    expect(projectStageIndex("development_frontend")).toBe(5);
    expect(projectStages[5].detail).toBe("后端 → 前端");
    expect(projectStages[5].displayName).toBe("开发");
    expect(projectInternalStageLabel("development_backend")).toBe("后端开发");
    expect(projectInternalStageLabel("development_frontend")).toBe("前端开发");
    expect(projectStageLabel("alignment")).toBe("项目对齐");
  });
});
