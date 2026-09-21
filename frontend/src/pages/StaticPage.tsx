import { Disclaimer } from "@/components/Disclaimer";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

import { PublicHeader } from "./parts/PublicHeader";

export interface StaticSection {
  heading: string;
  body: string[];
}

/**
 * A public prose page. Methodology and limitations are the pages where this
 * product earns the word "transparent", so they are plain text with no
 * decoration competing for attention.
 */
export function StaticPage({
  eyebrow,
  title,
  lede,
  sections,
}: {
  eyebrow: string;
  title: string;
  lede: string;
  sections: StaticSection[];
}) {
  useDocumentTitle(title);

  return (
    <>
      <PublicHeader />
      <main id="main" className="mx-auto max-w-[1440px] px-4 pt-32 pb-24 md:px-8 lg:px-16">
        <div className="max-w-[680px]">
          <p className="hm-eyebrow mb-6">{eyebrow}</p>
          <h1 className="font-display text-ink text-[length:var(--text-3xl)] leading-tight font-light">
            {title}
          </h1>
          <p className="text-ink-muted mt-6 text-lg leading-relaxed">{lede}</p>

          {sections.map((section) => (
            <section key={section.heading} className="border-line mt-12 border-t pt-8">
              <h2 className="text-ink text-xl font-medium">{section.heading}</h2>
              {section.body.map((paragraph) => (
                <p key={paragraph} className="text-ink-muted mt-4 text-sm leading-relaxed">
                  {paragraph}
                </p>
              ))}
            </section>
          ))}

          <Disclaimer className="border-line mt-16 border-t pt-8" />
        </div>
      </main>
    </>
  );
}
