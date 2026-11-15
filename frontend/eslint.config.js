import { defineConfig } from 'eslint/config';
import eslintConfigPrettier from 'eslint-config-prettier/flat';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import simpleImportSort from 'eslint-plugin-simple-import-sort';
import globals from 'globals';
import ts from 'typescript-eslint';
import js from '@eslint/js';

const tslint = defineConfig({
    files: ['src/**/*.ts', 'src/**/*.tsx'],
    extends: [js.configs.recommended, ts.configs.recommendedTypeChecked],
    plugins: {
        '@typescript-eslint': ts.plugin,
    },
    languageOptions: {
        parserOptions: {
            projectService: true,
            tsconfigRootDir: import.meta.dirname,
        },
    },
    rules: {
        '@typescript-eslint/no-unused-expressions': 'warn',
        '@typescript-eslint/no-confusing-void-expression': 'off',
        '@typescript-eslint/use-unknown-in-catch-callback-variable': 'off',
        '@typescript-eslint/restrict-template-expressions': 'off',
        '@typescript-eslint/no-unnecessary-type-parameters': 'off',
        '@typescript-eslint/no-unnecessary-condition': 'off',
        '@typescript-eslint/restrict-plus-operands': 'off',
        '@typescript-eslint/unbound-method': 'off',
        '@typescript-eslint/no-floating-promises': [
            'error',
            {
                ignoreVoid: true,
            },
        ],
        '@typescript-eslint/no-misused-promises': [
            'error',
            {
                checksVoidReturn: false,
            },
        ],
        '@typescript-eslint/no-unused-vars': [
            'warn',
            { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
        ],
    },
});

/** Custom plugin to warn using icons outside the icon component */
const IconUsagePlugin = {
    meta: {
        name: 'no-lucide-outside-icon',
        version: '1.0.0',
    },
    rules: {
        'no-lucide-outside-icon': {
            create(context) {
                return {
                    ImportDeclaration(node) {
                        const filePath = context.getFilename();
                        const isIconsFile =
                            filePath.endsWith('icons.ts') ||
                            filePath.endsWith('icons.tsx'); // in case you use TSX

                        if (
                            !isIconsFile &&
                            node.source.value === 'lucide-react'
                        ) {
                            context.report({
                                node,
                                message:
                                    "Importing lucide icons outside 'icons.ts' is not allowed.",
                            });
                        }
                    },
                };
            },
        },
    },
};

export default defineConfig(
    // global ignores
    {
        ignores: [
            'dist/',
            'node_modules/',
            'src/pythonTypes.d.ts',
            'dev-dist/',
        ],
    },

    // global variables, applies to everything
    {
        languageOptions: {
            globals: {
                ...globals.browser,
            },
        },
    },

    // apply tslint to ts files
    tslint,

    // Adding simple-import-sort to the eslint config
    {
        plugins: {
            'simple-import-sort': simpleImportSort,
        },
        rules: {
            'simple-import-sort/imports': [
                'warn',
                {
                    groups: [
                        // External modules
                        ['^\\w', '^@[a-z]'],
                        // Internal modules
                        ['^@/[a-z]'],
                        ['^src'],
                        ['^\\.'],
                        // Styles (ending with .css, .scss, .sass, or .less)
                        // image imports might also have a media query
                        [
                            '^.+\\.(css|scss|sass|less)$',
                            '^.+\\.(jpg|jpeg|png|gif|svg)*\\?*',
                        ],
                    ],
                },
            ],
        },
    },

    // Adding react to the eslint config
    {
        plugins: {
            react,
            'react-hooks': reactHooks,
        },
        rules: {
            'react-hooks/rules-of-hooks': 'error',
            'react-hooks/exhaustive-deps': 'warn',
        },
    },

    // apply prettier
    eslintConfigPrettier,

    // apply react-refresh
    {
        languageOptions: {
            globals: {
                ...globals.node,
            },
        },
        plugins: {
            'react-refresh': reactRefresh,
        },
        rules: {
            'react-refresh/only-export-components': [
                process.env.CI ? 'off' : 'warn',
                {
                    allowConstantExport: true,
                    extraHOCs: [
                        // Tanstack
                        'createFileRoute',
                        'createRootRouteWithContext',
                        // MUI
                        'styled',
                    ],
                },
            ],
        },
    },
    {
        files: ['**/*context.ts*'],
        rules: {
            'react-refresh/only-export-components': 'off',
        },
    },
    {
        plugins: {
            'icon-usage': IconUsagePlugin,
        },
        rules: {
            // We should on working to enable this rule
            'icon-usage/no-lucide-outside-icon': 'off',
        },
    }
);
