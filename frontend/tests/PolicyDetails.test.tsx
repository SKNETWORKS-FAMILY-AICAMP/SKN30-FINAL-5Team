import {
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react-native';
import { Text } from 'react-native';
import { readFileSync } from 'fs';
import { join } from 'path';
import { OnboardingScreen } from '../src/features/onboarding/OnboardingScreen';
import { onboardingPreviewApi } from '../src/features/preview/onboardingPreview';

import {
  PolicyDetails,
  PolicyMarkdown,
} from '../src/features/onboarding/PolicyDetails';
import {
  POLICY_DOCUMENTS,
  type PolicyDocumentId,
} from '../src/policy_docs/documents';

const visibleSource = (source: string) =>
  source
    .replace(/^\|[\s:|\-]+\|$/gm, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '•')
    .replace(/\*\*/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[|\s]/g, '');

describe('policy source rendering', () => {
  it('keeps each disclosure inside its own consent box without changing agreement', () => {
    render(
      <OnboardingScreen
        api={onboardingPreviewApi}
        initialStep={8}
        onCompleted={jest.fn()}
        onSignOut={jest.fn()}
      />,
    );
    for (const id of Object.keys(POLICY_DOCUMENTS) as PolicyDocumentId[]) {
      const box = within(screen.getByTestId(`consent-box-${id}`));
      const checkbox = box.getByRole('checkbox');
      fireEvent.press(
        box.getByRole('button', {
          name: `${POLICY_DOCUMENTS[id].title} 펼쳐보기`,
        }),
      );
      expect(checkbox).not.toBeChecked();
      fireEvent.press(checkbox);
      expect(checkbox).toBeChecked();
      expect(
        box.getByRole('button', { name: `${POLICY_DOCUMENTS[id].title} 접기` }),
      ).toBeOnTheScreen();
    }
  });
  it.each(Object.keys(POLICY_DOCUMENTS) as PolicyDocumentId[])(
    'renders every word and table cell of %s from the original file',
    (id) => {
      const document = POLICY_DOCUMENTS[id];
      expect(document.markdown).toBe(
        readFileSync(
          join(__dirname, '../src/policy_docs', document.filename),
          'utf8',
        ),
      );
      const result = render(
        <PolicyMarkdown markdown={document.markdown} onLink={jest.fn()} />,
      );
      const roots = result.UNSAFE_getAllByType(Text).filter((node) => {
        let parent = node.parent;
        while (parent) {
          if (parent.type === Text) return false;
          parent = parent.parent;
        }
        return true;
      });
      const textContent = (children: unknown): string =>
        Array.isArray(children)
          ? children.map(textContent).join('')
          : typeof children === 'string' || typeof children === 'number'
            ? String(children)
            : children && typeof children === 'object' && 'props' in children
              ? textContent(
                  (children as { props: { children: unknown } }).props.children,
                )
              : '';
      expect(
        roots
          .map((node) => textContent(node.props.children))
          .join('')
          .replace(/\s/g, ''),
      ).toBe(visibleSource(document.markdown));
      if (document.markdown.includes('|---'))
        expect(
          screen.getAllByLabelText('약관 표, 가로로 스크롤하여 전체 내용 확인')
            .length,
        ).toBeGreaterThan(0);
    },
  );

  it('opens and closes each full policy independently without a consent checkbox', () => {
    render(
      <>
        <PolicyDetails documentId="service_terms" />
        <PolicyDetails documentId="sensitive_data" />
      </>,
    );
    expect(screen.queryByTestId('policy-service_terms')).toBeNull();
    fireEvent.press(
      screen.getByRole('button', { name: '서비스 이용약관 펼쳐보기' }),
    );
    expect(screen.getByTestId('policy-service_terms')).toBeOnTheScreen();
    expect(screen.queryByTestId('policy-sensitive_data')).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.press(
      screen.getByRole('button', { name: '서비스 이용약관 접기' }),
    );
    expect(screen.queryByTestId('policy-service_terms')).toBeNull();
  });

  it('opens a linked local policy without leaving onboarding', () => {
    render(<PolicyDetails documentId="general_personal_data" />);
    fireEvent.press(
      screen.getByRole('button', { name: '개인정보 수집 및 이용 펼쳐보기' }),
    );
    fireEvent.press(
      screen.getByRole('link', { name: '민감정보 수집·이용 동의' }),
    );
    expect(
      screen.getByRole('button', { name: '연결된 약관 닫기' }),
    ).toBeOnTheScreen();
    expect(
      screen.getByRole('header', { name: '민감정보 수집·이용 동의' }),
    ).toBeOnTheScreen();
  });
});
