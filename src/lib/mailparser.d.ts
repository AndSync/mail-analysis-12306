declare module "mailparser" {
  export interface ParsedMail {
    subject?: string;
    text?: string | false;
    html?: string | false;
    from?: { text?: string; value?: Array<{ address?: string; name?: string }> };
    headers: Map<string, string>;
  }
  export function simpleParser(source: Buffer | string, options?: unknown): Promise<ParsedMail>;
}
