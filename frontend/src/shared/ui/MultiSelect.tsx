import { Select } from "antd";
import type { DefaultOptionType, SelectProps } from "antd/es/select";

export type MultiSelectProps = Omit<SelectProps<string[], DefaultOptionType>, "mode">;

export function MultiSelect({
  allowClear = true,
  optionFilterProp = "label",
  placeholder = "请选择",
  ...props
}: MultiSelectProps) {
  return (
    <Select
      {...props}
      allowClear={allowClear}
      mode="multiple"
      optionFilterProp={optionFilterProp}
      placeholder={placeholder}
    />
  );
}
