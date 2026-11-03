# Icon Standard

前端图标统一从本目录导出，不在页面或业务组件中直接散落导入图标库。

当前选型：

```text
@icon-park/react
```

使用约束：

- 页面组件只能从 `src/shared/icons` 导入图标。
- 不在业务组件中直接写 SVG。
- 不在业务组件中直接从 `@icon-park/react` 导入图标。
- 默认使用 `theme="outline"`，除非设计明确要求 filled、two-tone 或 multi-color。
- 调用方只使用 `AppIconSize`（`xs` 至 `3xl`）语义尺寸，不传像素值。
- `AppIcon` 负责图标的尺寸盒、行高和 SVG 显示方式；页面不得通过 margin 或 vertical-align 修正图标位置。
- 图标尺寸、颜色应跟随按钮、菜单、状态组件的设计 token。

风险边界：

- IconPark 仓库已归档，只适合作为当前阶段稳定图标源。
- 如果后续发现维护、安全或兼容问题，应只替换本目录封装，不扩散到页面层。
