export const agentTypes = [
  {
    key: "functional",
    name: "功能型",
    description: "面向复杂任务的自主推理，可使用本地沙盒执行环境。",
    is_default: false,
    uses_knowledge: false,
    restricts_executable_skills: false,
  },
  {
    key: "knowledge",
    name: "知识型",
    description: "优先检索、理解和整合知识内容，不提供本地执行环境。",
    is_default: true,
    uses_knowledge: true,
    restricts_executable_skills: true,
  },
];
