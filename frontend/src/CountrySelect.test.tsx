import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach } from "vitest";
import { describe, expect, it, vi } from "vitest";
import CountrySelect from "./CountrySelect";

afterEach(cleanup);

describe("CountrySelect", () => {
  it("searches by country name and returns its ISO-2 code", () => {
    const onChange = vi.fn();
    render(<CountrySelect value="AU" onChange={onChange} />);

    const input = screen.getByRole("combobox", { name: "Страна · ISO-2" });
    fireEvent.change(input, { target: { value: "canada" } });
    fireEvent.click(screen.getByRole("option", { name: /Канада.*CA/ }));

    expect(onChange).toHaveBeenCalledWith("CA");
  });

  it("searches by ISO-2 code and supports keyboard selection", () => {
    const onChange = vi.fn();
    render(<CountrySelect value="AU" onChange={onChange} />);

    const input = screen.getByRole("combobox", { name: "Страна · ISO-2" });
    fireEvent.change(input, { target: { value: "NZ" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith("NZ");
  });
});
