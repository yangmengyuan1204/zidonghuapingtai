<template>
  <main class="v2-lab">
    <header class="v2-lab__header">
      <div>
        <p class="v2-lab__eyebrow">Local development only</p>
        <h1 class="v2-lab__title">Frontend V2 Base Components</h1>
        <p class="v2-lab__intro">
          Phase 5.2A–5.5C 独立人工验收页，不连接 Router、Pinia 或后端 API。
        </p>
      </div>
      <BaseBadge tone="info" dot>18 base components ready</BaseBadge>
    </header>

    <section class="v2-lab__section" aria-labelledby="lab-buttons">
      <div class="v2-lab__section-heading">
        <h2 id="lab-buttons">BaseButton</h2>
        <span>clicks: {{ buttonClicks }}</span>
      </div>
      <div class="v2-lab__row">
        <BaseButton data-testid="button-primary" @click="buttonClicks += 1">Primary</BaseButton>
        <BaseButton variant="secondary">Secondary</BaseButton>
        <BaseButton variant="ghost">Ghost</BaseButton>
        <BaseButton variant="danger">Danger</BaseButton>
        <BaseButton size="compact">Compact</BaseButton>
        <BaseButton disabled data-testid="button-disabled">Disabled</BaseButton>
        <BaseButton loading data-testid="button-loading">Loading action</BaseButton>
        <BaseButton variant="secondary">
          <template #icon><LabIcon /></template>
          Icon + Text
        </BaseButton>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-icon-buttons">
      <div class="v2-lab__section-heading">
        <h2 id="lab-icon-buttons">BaseIconButton</h2>
        <span>clicks: {{ iconButtonClicks }}</span>
      </div>
      <div class="v2-lab__row">
        <BaseIconButton
          label="打开搜索"
          data-testid="icon-button-default"
          @click="iconButtonClicks += 1"
        >
          <LabIcon />
        </BaseIconButton>
        <BaseIconButton
          label="固定筛选"
          variant="secondary"
          :pressed="iconPressed"
          data-testid="icon-button-pressed"
          @click="toggleIconPressed"
        >
          <LabIcon />
        </BaseIconButton>
        <BaseIconButton label="不可用操作" disabled data-testid="icon-button-disabled">
          <LabIcon />
        </BaseIconButton>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-inputs">
      <div class="v2-lab__section-heading">
        <h2 id="lab-inputs">BaseInput</h2>
        <span>native input semantics</span>
      </div>
      <div class="v2-lab__grid">
        <BaseInput v-model="normalInput" label="Normal" placeholder="输入内容" />
        <BaseInput v-model="labeledInput" label="With Label" required />
        <BaseInput v-model="prefixInput" label="Prefix" help="支持按名称搜索">
          <template #prefix><LabIcon /></template>
        </BaseInput>
        <BaseInput v-model="suffixInput" label="Suffix">
          <template #suffix><span>.json</span></template>
        </BaseInput>
        <BaseInput
          v-model="errorInput"
          label="Error"
          error="请输入有效的用例名称"
          data-testid="input-error"
        />
        <BaseInput model-value="不可编辑" label="Disabled" disabled />
        <BaseInput model-value="只读内容" label="Readonly" readonly />
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-selects">
      <div class="v2-lab__section-heading">
        <h2 id="lab-selects">BaseSelect</h2>
        <span>native keyboard and form semantics</span>
      </div>
      <div class="v2-lab__control-grid">
        <div class="v2-lab__example">
          <strong>Default</strong>
          <BaseSelect
            v-model="selectDefault"
            :options="selectOptions"
            aria-label="Default environment"
            data-testid="select-default"
          />
        </div>
        <div class="v2-lab__example">
          <strong>With label</strong>
          <BaseSelect
            v-model="selectLabeled"
            label="Environment"
            :options="selectOptions"
            data-testid="select-label"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Placeholder</strong>
          <BaseSelect
            v-model="selectPlaceholder"
            placeholder="Choose an environment"
            :options="selectOptions"
            aria-label="Environment with placeholder"
            data-testid="select-placeholder"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Selected</strong>
          <BaseSelect
            v-model="selectSelected"
            label="Release target"
            :options="selectOptions"
            data-testid="select-selected"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Hover</strong>
          <BaseSelect
            v-model="selectHover"
            :options="selectOptions"
            aria-label="Hover state preview"
            data-testid="select-hover"
          />
          <small>Move the pointer over the native control.</small>
        </div>
        <div class="v2-lab__example">
          <strong>Focus</strong>
          <BaseSelect
            v-model="selectFocus"
            :options="selectOptions"
            aria-label="Focus state preview"
            data-testid="select-focus"
          />
          <small>Use Tab, Arrow keys, Enter, and Escape.</small>
        </div>
        <div class="v2-lab__example">
          <strong>Disabled</strong>
          <BaseSelect
            model-value="test"
            label="Locked environment"
            :options="selectOptions"
            disabled
            data-testid="select-disabled"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Required</strong>
          <BaseSelect
            v-model="selectRequired"
            label="Required environment"
            placeholder="Choose one"
            :options="selectOptions"
            required
            data-testid="select-required"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Error</strong>
          <BaseSelect
            v-model="selectError"
            label="Environment"
            placeholder="Choose one"
            :options="selectOptions"
            error="Select an environment before continuing."
            data-testid="select-error"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Long option text</strong>
          <BaseSelect
            v-model="selectLong"
            label="Deployment destination"
            :options="longSelectOptions"
            data-testid="select-long"
          />
        </div>
        <div class="v2-lab__example v2-lab__narrow">
          <strong>Narrow container</strong>
          <BaseSelect
            v-model="selectNarrow"
            label="Environment"
            :options="longSelectOptions"
            data-testid="select-narrow"
          />
        </div>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-textareas">
      <div class="v2-lab__section-heading">
        <h2 id="lab-textareas">BaseTextarea</h2>
        <span>native multiline input and quiet metadata</span>
      </div>
      <div class="v2-lab__control-grid">
        <div class="v2-lab__example">
          <strong>Default</strong>
          <BaseTextarea
            v-model="textareaDefault"
            aria-label="Default request body"
            data-testid="textarea-default"
          />
        </div>
        <div class="v2-lab__example">
          <strong>With label</strong>
          <BaseTextarea
            v-model="textareaLabeled"
            label="Request body"
            help="Plain text or JSON accepted by the caller."
            data-testid="textarea-label"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Placeholder</strong>
          <BaseTextarea
            v-model="textareaPlaceholder"
            placeholder="Enter request content"
            aria-label="Request content with placeholder"
            data-testid="textarea-placeholder"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Focus</strong>
          <BaseTextarea
            v-model="textareaFocus"
            label="Focus preview"
            data-testid="textarea-focus"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Disabled</strong>
          <BaseTextarea
            model-value="Editing is unavailable."
            label="Disabled content"
            disabled
            data-testid="textarea-disabled"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Readonly</strong>
          <BaseTextarea
            model-value="This value remains selectable and readable."
            label="Readonly content"
            readonly
            data-testid="textarea-readonly"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Error</strong>
          <BaseTextarea
            v-model="textareaError"
            label="Assertion"
            error="Enter a valid assertion before continuing."
            data-testid="textarea-error"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Maxlength</strong>
          <BaseTextarea
            v-model="textareaMaxlength"
            label="Short description"
            :maxlength="80"
            data-testid="textarea-maxlength"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Long content</strong>
          <BaseTextarea
            v-model="textareaLong"
            label="Execution notes"
            :rows="6"
            data-testid="textarea-long"
          />
        </div>
        <div class="v2-lab__example v2-lab__narrow">
          <strong>Narrow container</strong>
          <BaseTextarea
            v-model="textareaNarrow"
            label="Compact notes"
            :maxlength="120"
            error="Review the content."
            data-testid="textarea-narrow"
          />
        </div>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-checkboxes">
      <div class="v2-lab__section-heading">
        <h2 id="lab-checkboxes">BaseCheckbox</h2>
        <span>checked: {{ checkboxValue }}</span>
      </div>
      <div class="v2-lab__stack">
        <BaseCheckbox
          v-model="checkboxValue"
          label="Unchecked / Checked"
          data-testid="checkbox-toggle"
        />
        <BaseCheckbox model-value label="Checked" />
        <BaseCheckbox
          v-model="indeterminateValue"
          label="Indeterminate"
          indeterminate
          data-testid="checkbox-indeterminate"
        />
        <BaseCheckbox model-value label="Disabled" disabled />
        <BaseCheckbox
          v-model="describedCheckbox"
          label="With description"
          description="Space 键应切换原生 checkbox 状态"
        />
        <BaseCheckbox
          v-model="labelOnlyCheckbox"
          id="lab-checkbox-aria"
          aria-label="仅复选框示例"
          data-testid="checkbox-aria-label"
        />
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-badges">
      <div class="v2-lab__section-heading">
        <h2 id="lab-badges">BaseBadge</h2>
        <span>status display only</span>
      </div>
      <div class="v2-lab__row">
        <BaseBadge>Neutral</BaseBadge>
        <BaseBadge tone="success">Success</BaseBadge>
        <BaseBadge tone="warning">Warning</BaseBadge>
        <BaseBadge tone="danger">Danger</BaseBadge>
        <BaseBadge tone="info">Info</BaseBadge>
        <BaseBadge tone="success" dot>Operational</BaseBadge>
        <BaseBadge size="compact">Compact</BaseBadge>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-chips">
      <div class="v2-lab__section-heading">
        <h2 id="lab-chips">BaseChip</h2>
        <span>select events: {{ chipSelectCount }}</span>
      </div>
      <div class="v2-lab__row">
        <BaseChip
          :selected="chipSelected"
          data-testid="chip-toggle"
          @select="toggleChip"
        >
          Default
        </BaseChip>
        <BaseChip selected>Selected</BaseChip>
        <BaseChip count="18">
          <template #icon><LabIcon /></template>
          Count
        </BaseChip>
        <BaseChip disabled data-testid="chip-disabled">Disabled</BaseChip>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-cards">
      <div class="v2-lab__section-heading">
        <h2 id="lab-cards">BaseCard</h2>
        <span>activations: {{ cardActivations }}</span>
      </div>
      <div class="v2-lab__grid">
        <BaseCard>
          <template #header><strong>Surface</strong></template>
          默认 Surface Card
          <template #footer><small>Default padding</small></template>
        </BaseCard>
        <BaseCard variant="soft">
          <template #header><strong>Soft</strong></template>
          柔和背景容器
        </BaseCard>
        <BaseCard padding="compact">
          <strong>Compact</strong>
        </BaseCard>
        <BaseCard padding="spacious">
          <strong>Spacious</strong>
          <span>更宽松的内容间距</span>
        </BaseCard>
        <BaseCard
          as="article"
          interactive
          data-testid="card-interactive"
          @activate="cardActivations += 1"
        >
          <template #header><strong>Interactive</strong></template>
          使用 Tab 聚焦，Enter 或 Space 激活。
        </BaseCard>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-dropdowns">
      <div class="v2-lab__section-heading">
        <h2 id="lab-dropdowns">BaseDropdown</h2>
        <span>select events: {{ dropdownSelectCount }} · last: {{ dropdownLastValue }}</span>
      </div>

      <div class="v2-lab__dropdown-grid">
        <div class="v2-lab__example">
          <strong>bottom-start</strong>
          <BaseDropdown
            v-model:open="bottomStartOpen"
            placement="bottom-start"
            aria-label="Bottom start menu"
            @select="handleDropdownSelect"
          >
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-bottom-start-trigger">
                Bottom start
              </BaseButton>
            </template>
            <BaseDropdownItem value="bottom-start-edit">Edit</BaseDropdownItem>
            <BaseDropdownItem value="bottom-start-copy">Duplicate</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>bottom-end</strong>
          <BaseDropdown
            v-model:open="bottomEndOpen"
            placement="bottom-end"
            aria-label="Bottom end menu"
            @select="handleDropdownSelect"
          >
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-bottom-end-trigger">
                Bottom end
              </BaseButton>
            </template>
            <BaseDropdownItem value="bottom-end-edit">Edit</BaseDropdownItem>
            <BaseDropdownItem value="bottom-end-copy">Duplicate</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>top-start</strong>
          <BaseDropdown
            v-model:open="topStartOpen"
            placement="top-start"
            aria-label="Top start menu"
            @select="handleDropdownSelect"
          >
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-top-start-trigger">
                Top start
              </BaseButton>
            </template>
            <BaseDropdownItem value="top-start-edit">Edit</BaseDropdownItem>
            <BaseDropdownItem value="top-start-copy">Duplicate</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>top-end</strong>
          <BaseDropdown
            v-model:open="topEndOpen"
            placement="top-end"
            aria-label="Top end menu"
            @select="handleDropdownSelect"
          >
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-top-end-trigger">
                Top end
              </BaseButton>
            </template>
            <BaseDropdownItem value="top-end-edit">Edit</BaseDropdownItem>
            <BaseDropdownItem value="top-end-copy">Duplicate</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>Disabled trigger</strong>
          <BaseDropdown v-model:open="disabledTriggerOpen" disabled aria-label="Disabled dropdown">
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-disabled-trigger">
                Disabled trigger
              </BaseButton>
            </template>
            <BaseDropdownItem value="disabled-trigger-item">Unavailable</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>Item states</strong>
          <BaseDropdown v-model:open="itemStatesOpen" aria-label="Item states menu" @select="handleDropdownSelect">
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-item-states-trigger">
                Item states
              </BaseButton>
            </template>
            <BaseDropdownItem value="icon" data-testid="dropdown-icon-item">
              <template #icon><LabIcon /></template>
              Icon item
            </BaseDropdownItem>
            <BaseDropdownItem value="suffix" data-testid="dropdown-suffix-item">
              With suffix
              <template #suffix>⌘E</template>
            </BaseDropdownItem>
            <BaseDropdownItem value="disabled" disabled data-testid="dropdown-disabled-item">
              Disabled item
            </BaseDropdownItem>
            <BaseDropdownItem value="danger" danger data-testid="dropdown-danger-item">
              Delete
            </BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>closeOnSelect=false</strong>
          <BaseDropdown
            v-model:open="keepOpenOnSelect"
            :close-on-select="false"
            aria-label="Keep open menu"
            data-testid="dropdown-keep-open"
            @select="handleDropdownSelect"
          >
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-keep-open-trigger">
                Keep open
              </BaseButton>
            </template>
            <BaseDropdownItem value="keep-open">Select without closing</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>closeOnOutside=false</strong>
          <BaseDropdown
            v-model:open="ignoreOutsideOpen"
            :close-on-outside="false"
            aria-label="Ignore outside menu"
            data-testid="dropdown-ignore-outside"
          >
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-ignore-outside-trigger">
                Ignore outside
              </BaseButton>
            </template>
            <BaseDropdownItem value="persistent">Remains open</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>matchTriggerWidth</strong>
          <BaseDropdown
            v-model:open="matchWidthOpen"
            match-trigger-width
            aria-label="Matched width menu"
            data-testid="dropdown-match-width"
          >
            <template #trigger>
              <BaseButton class="v2-lab__wide-trigger" variant="secondary" size="compact" data-testid="dropdown-match-width-trigger">
                Match this wider trigger
              </BaseButton>
            </template>
            <BaseDropdownItem value="matched">Matched menu width</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>No available items</strong>
          <BaseDropdown v-model:open="noItemsOpen" aria-label="No available items menu" data-testid="dropdown-no-items">
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-no-items-trigger">
                No available items
              </BaseButton>
            </template>
            <BaseDropdownItem value="none-a" disabled>Disabled A</BaseDropdownItem>
            <BaseDropdownItem value="none-b" disabled>Disabled B</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>Long text</strong>
          <BaseDropdown v-model:open="longTextOpen" aria-label="Long text menu" data-testid="dropdown-long-text">
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-long-text-trigger">
                Long text
              </BaseButton>
            </template>
            <BaseDropdownItem value="long-text">
              This is an intentionally long menu item that must remain inside the viewport
            </BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example v2-lab__edge">
          <strong>Viewport edge</strong>
          <BaseDropdown
            v-model:open="viewportEdgeOpen"
            placement="bottom-end"
            aria-label="Viewport edge menu"
            data-testid="dropdown-viewport-edge"
          >
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-viewport-edge-trigger">
                Right edge
              </BaseButton>
            </template>
            <BaseDropdownItem value="edge">Clamped to viewport</BaseDropdownItem>
          </BaseDropdown>
        </div>

        <div class="v2-lab__example">
          <strong>Mutual exclusion</strong>
          <div class="v2-lab__row">
            <BaseDropdown v-model:open="mutualAOpen" aria-label="Mutual menu A" data-testid="dropdown-mutual-a">
              <template #trigger>
                <BaseButton variant="secondary" size="compact" data-testid="dropdown-mutual-a-trigger">Menu A</BaseButton>
              </template>
              <BaseDropdownItem value="mutual-a">A item</BaseDropdownItem>
            </BaseDropdown>
            <BaseDropdown v-model:open="mutualBOpen" aria-label="Mutual menu B" data-testid="dropdown-mutual-b">
              <template #trigger>
                <BaseButton variant="secondary" size="compact" data-testid="dropdown-mutual-b-trigger">Menu B</BaseButton>
              </template>
              <BaseDropdownItem value="mutual-b">B item</BaseDropdownItem>
            </BaseDropdown>
          </div>
        </div>

        <div class="v2-lab__example">
          <strong>Unmount while open</strong>
          <BaseDropdown
            v-if="showUnmountDropdown"
            v-model:open="unmountDropdownOpen"
            aria-label="Unmount menu"
            data-testid="dropdown-unmount"
          >
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-unmount-trigger">
                Open before unmount
              </BaseButton>
            </template>
            <BaseDropdownItem value="unmount">Unmount item</BaseDropdownItem>
          </BaseDropdown>
          <BaseButton variant="ghost" size="compact" data-testid="dropdown-unmount-control" @click="showUnmountDropdown = false">
            Unmount Dropdown
          </BaseButton>
        </div>

        <div class="v2-lab__example">
          <strong>Externally controlled</strong>
          <div class="v2-lab__row">
            <BaseButton variant="ghost" size="compact" data-testid="dropdown-controlled-open" @click="controlledOpen = true">Open</BaseButton>
            <BaseButton variant="ghost" size="compact" data-testid="dropdown-controlled-close" @click="controlledOpen = false">Close</BaseButton>
          </div>
          <BaseDropdown v-model:open="controlledOpen" aria-label="Controlled menu" data-testid="dropdown-controlled">
            <template #trigger>
              <BaseButton variant="secondary" size="compact" data-testid="dropdown-controlled-trigger">
                Controlled trigger
              </BaseButton>
            </template>
            <BaseDropdownItem value="controlled" @select="handleDropdownSelect">Controlled item</BaseDropdownItem>
          </BaseDropdown>
        </div>
      </div>

      <button class="v2-lab__outside-target" type="button" data-testid="dropdown-outside-target">
        Outside click target
      </button>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-pagination">
      <div class="v2-lab__section-heading">
        <h2 id="lab-pagination">BasePagination</h2>
        <span>change events: {{ paginationEvents }}</span>
      </div>
      <div class="v2-lab__showcase-grid">
        <div class="v2-lab__example">
          <strong>Single page</strong>
          <BasePagination :page="1" :total="0" :page-size="20" aria-label="单页分页" />
        </div>
        <div class="v2-lab__example">
          <strong>Few pages</strong>
          <BasePagination :page="2" :total="50" :page-size="10" aria-label="少量页分页" />
        </div>
        <div class="v2-lab__example">
          <strong>Near start / First</strong>
          <BasePagination :page="2" :total="1000" :page-size="10" aria-label="靠前分页" />
          <BasePagination
            :page="1"
            :total="1000"
            :page-size="10"
            aria-label="第一页分页"
            data-testid="pagination-first"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Center / Interactive</strong>
          <BasePagination
            :page="paginationPage"
            :total="1000"
            :page-size="10"
            aria-label="交互分页"
            data-testid="pagination-interactive"
            @change="handlePaginationChange"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Near end / Last</strong>
          <BasePagination :page="99" :total="1000" :page-size="10" aria-label="靠后分页" />
          <BasePagination
            :page="100"
            :total="1000"
            :page-size="10"
            aria-label="最后一页分页"
            data-testid="pagination-last"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Disabled</strong>
          <BasePagination
            :page="50"
            :total="1000"
            :page-size="10"
            disabled
            aria-label="禁用分页"
            data-testid="pagination-disabled"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Huge total</strong>
          <BasePagination
            :page="500000"
            :total="10000000"
            :page-size="10"
            aria-label="超大分页"
            data-testid="pagination-huge"
          />
        </div>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-tables">
      <div class="v2-lab__section-heading">
        <h2 id="lab-tables">BaseTable</h2>
        <span>semantic data table with responsive overflow</span>
      </div>
      <div class="v2-lab__table-stack">
        <div class="v2-lab__example">
          <strong>Normal rows</strong>
          <BaseTable
            :columns="simpleTableColumns"
            :rows="simpleTableRows"
            aria-label="Normal resource rows"
            data-testid="table-normal"
          />
        </div>

        <div class="v2-lab__example">
          <strong>Dense real-business content · Method / Status · Actions</strong>
          <BaseTable
            :columns="resourceTableColumns"
            :rows="resourceTableRows"
            :min-content-width="1080"
            aria-label="Dense API case resources"
            data-testid="table-dense"
          >
            <template #case="{ row }">
              <div class="v2-lab__table-primary">
                <strong>{{ row.case }}</strong>
                <span>{{ row.path }}</span>
              </div>
            </template>
            <template #method="{ row }">
              <span data-testid="table-method-status">
                <BaseBadge size="compact">{{ row.method }}</BaseBadge>
              </span>
            </template>
            <template #status="{ row }">
              <BaseBadge :tone="row.statusTone" size="compact">{{ row.status }}</BaseBadge>
            </template>
            <template #actions="{ row }">
              <div class="v2-lab__table-actions" data-testid="table-actions">
                <BaseButton size="compact">Run</BaseButton>
                <BaseButton variant="secondary" size="compact" :aria-label="`Edit ${row.case}`">Edit</BaseButton>
              </div>
            </template>
          </BaseTable>
        </div>

        <div class="v2-lab__example">
          <strong>Long text</strong>
          <BaseTable
            :columns="longTableColumns"
            :rows="longTableRows"
            :min-content-width="920"
            aria-label="Long resource content"
            data-testid="table-long"
          />
        </div>

        <div class="v2-lab__table-state-grid">
          <div class="v2-lab__example">
            <strong>Empty slot</strong>
            <BaseTable
              :columns="simpleTableColumns"
              :rows="[]"
              aria-label="Empty resources"
              data-testid="table-empty"
            >
              <template #empty>
                <span>No resource records match the current scope.</span>
              </template>
            </BaseTable>
          </div>
          <div class="v2-lab__example">
            <strong>Loading slot</strong>
            <BaseTable
              :columns="simpleTableColumns"
              :rows="[]"
              loading
              aria-label="Loading resources"
              data-testid="table-loading"
            >
              <template #loading>
                <div class="v2-lab__table-loading" role="status">
                  <BaseSkeleton :lines="3" />
                  <span>Loading resources</span>
                </div>
              </template>
            </BaseTable>
          </div>
        </div>

        <div class="v2-lab__example v2-lab__overflow-frame">
          <strong>Horizontal overflow · 1080px minimum content</strong>
          <BaseTable
            :columns="resourceTableColumns"
            :rows="resourceTableRows"
            :min-content-width="1080"
            aria-label="Responsive overflow resources"
            data-testid="table-overflow"
          >
            <template #case="{ row }">
              <div class="v2-lab__table-primary">
                <strong>{{ row.case }}</strong>
                <span>{{ row.path }}</span>
              </div>
            </template>
            <template #method="{ row }"><BaseBadge size="compact">{{ row.method }}</BaseBadge></template>
            <template #status="{ row }"><BaseBadge :tone="row.statusTone" size="compact">{{ row.status }}</BaseBadge></template>
            <template #actions="{ row }">
              <div class="v2-lab__table-actions">
                <BaseButton size="compact">Run</BaseButton>
                <BaseButton variant="secondary" size="compact" :aria-label="`Open ${row.case}`">Open</BaseButton>
              </div>
            </template>
          </BaseTable>
        </div>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-tooltips">
      <div class="v2-lab__section-heading">
        <h2 id="lab-tooltips">BaseTooltip</h2>
        <span>hover, focus, blur and Escape</span>
      </div>
      <div class="v2-lab__row v2-lab__tooltip-row">
        <BaseTooltip content="Top tooltip" placement="top" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-top-trigger">
            Top
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Right tooltip" placement="right" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-right-trigger">
            Right
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Bottom tooltip" placement="bottom" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-bottom-trigger">
            Bottom
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Left tooltip" placement="left" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-left-trigger">
            Left
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Keyboard focus tooltip" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-keyboard-trigger">
            Keyboard focus
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Disabled tooltip" disabled :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-disabled-trigger">
            Disabled tooltip
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-empty-trigger">
            Empty content
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip content="Shared multi-root tooltip" :delay="0">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-multi-first">
            Multi A
          </BaseButton>
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-multi-second">
            Multi B
          </BaseButton>
        </BaseTooltip>
        <BaseTooltip v-if="showUnmountTooltip" content="Pending unmount" :delay="1000">
          <BaseButton variant="secondary" size="compact" data-testid="tooltip-unmount-trigger">
            Unmount timer
          </BaseButton>
        </BaseTooltip>
        <BaseButton
          variant="ghost"
          size="compact"
          data-testid="tooltip-unmount-control"
          @click="showUnmountTooltip = false"
        >
          Unmount pending tooltip
        </BaseButton>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-skeletons">
      <div class="v2-lab__section-heading">
        <h2 id="lab-skeletons">BaseSkeleton</h2>
        <span>decorative loading placeholders</span>
      </div>
      <div class="v2-lab__grid">
        <div class="v2-lab__example">
          <strong>Text</strong>
          <BaseSkeleton width="80%" data-testid="skeleton-text" />
        </div>
        <div class="v2-lab__example">
          <strong>Multiple lines</strong>
          <BaseSkeleton :lines="4" data-testid="skeleton-lines" />
        </div>
        <div class="v2-lab__example">
          <strong>Circle</strong>
          <BaseSkeleton variant="circle" :width="48" data-testid="skeleton-circle" />
        </div>
        <div class="v2-lab__example">
          <strong>Rectangle</strong>
          <BaseSkeleton variant="rectangle" data-testid="skeleton-rectangle" />
        </div>
        <div class="v2-lab__example">
          <strong>Custom dimensions</strong>
          <BaseSkeleton
            variant="rectangle"
            width="70%"
            :height="72"
            data-testid="skeleton-custom"
          />
        </div>
        <div class="v2-lab__example">
          <strong>Non-animated</strong>
          <BaseSkeleton
            variant="rectangle"
            :animated="false"
            data-testid="skeleton-static"
          />
        </div>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-empty-states">
      <div class="v2-lab__section-heading">
        <h2 id="lab-empty-states">BaseEmptyState</h2>
        <span>actions: {{ emptyActionCount }}</span>
      </div>
      <div class="v2-lab__grid">
        <BaseCard padding="none">
          <BaseEmptyState title="暂无数据" description="创建第一条记录后会显示在这里。">
            <template #icon><LabIcon /></template>
          </BaseEmptyState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseEmptyState compact title="紧凑空状态" description="适用于较小容器。">
            <template #icon><LabIcon /></template>
          </BaseEmptyState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseEmptyState title="未找到匹配结果" description="请调整搜索词或筛选条件。">
            <template #icon><LabIcon /></template>
          </BaseEmptyState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseEmptyState
            title="还没有测试用例"
            description="创建用例以开始自动化验证。"
            data-testid="empty-with-action"
          >
            <template #icon><LabIcon /></template>
            <template #action>
              <BaseButton
                size="compact"
                data-testid="empty-action"
                @click="emptyActionCount += 1"
              >
                创建用例
              </BaseButton>
            </template>
          </BaseEmptyState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseEmptyState
            title="无操作空状态"
            description="此状态不渲染空 action 容器。"
            icon-hidden
            data-testid="empty-without-action"
          />
        </BaseCard>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-error-states">
      <div class="v2-lab__section-heading">
        <h2 id="lab-error-states">BaseErrorState</h2>
        <span>retry events: {{ retryCount }}</span>
      </div>
      <div class="v2-lab__grid">
        <BaseCard padding="none">
          <BaseErrorState
            title="加载失败"
            message="暂时无法获取数据，请稍后重试。"
            retryable
            data-testid="error-retryable"
            @retry="retryCount += 1"
          >
            <template #icon><LabIcon /></template>
          </BaseErrorState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            title="不可恢复错误"
            message="请联系管理员处理。"
            data-testid="error-non-retryable"
          />
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            title="正在重试"
            message="正在重新连接服务。"
            retryable
            busy
            data-testid="error-busy"
            @retry="retryCount += 1"
          />
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            compact
            title="紧凑错误状态"
            message="适用于较小容器。"
          />
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            title="需要其他操作"
            message="使用调用方提供的自定义 action。"
            retryable
            data-testid="error-custom-action"
          >
            <template #action>
              <BaseButton variant="secondary" size="compact">查看帮助</BaseButton>
            </template>
          </BaseErrorState>
        </BaseCard>
        <BaseCard padding="none">
          <BaseErrorState
            title="含错误详情"
            message="可读详情保持为普通内容。"
            data-testid="error-details"
          >
            <template #details>Request ID: demo-request</template>
          </BaseErrorState>
        </BaseCard>
      </div>
    </section>

    <section class="v2-lab__section" aria-labelledby="lab-modals">
      <div class="v2-lab__section-heading">
        <h2 id="lab-modals">BaseModal</h2>
        <span>controlled, nested, focus-contained overlay foundation</span>
      </div>

      <dl class="v2-lab__modal-proof" aria-label="Modal runtime proof">
        <div><dt>Modal count</dt><dd>{{ getOverlayCount('modal') }}</dd></div>
        <div><dt>Scroll lock count</dt><dd>{{ getBodyScrollLockCount() }}</dd></div>
        <div><dt>Focus element</dt><dd>{{ activeFocusElement }}</dd></div>
        <div><dt>Portal owner count</dt><dd>{{ getV2PortalOwnerCount() }}</dd></div>
        <div><dt>Last close reason</dt><dd>{{ modalLastCloseReason }}</dd></div>
      </dl>

      <div class="v2-lab__modal-grid">
        <div class="v2-lab__example">
          <strong>Default</strong>
          <BaseButton size="compact" @click="defaultModalOpen = true">Open default</BaseButton>
          <BaseModal
            v-model:open="defaultModalOpen"
            title="Review environment"
            data-testid="modal-default"
            @close="recordModalClose"
          >
            <p>Review the environment details before continuing.</p>
            <template #footer>
              <BaseButton variant="secondary" @click="defaultModalOpen = false">Cancel</BaseButton>
              <BaseButton @click="defaultModalOpen = false">Continue</BaseButton>
            </template>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Long Content</strong>
          <BaseButton size="compact" @click="longModalOpen = true">Open long content</BaseButton>
          <BaseModal
            v-model:open="longModalOpen"
            title="Long operational review content that demonstrates stable wrapping at narrow widths"
            description="The body scrolls inside the panel while the viewport remains locked."
            data-testid="modal-long-content"
            @close="recordModalClose"
          >
            <div class="v2-lab__modal-long-copy">
              <p v-for="index in 14" :key="index">
                Section {{ index }} preserves a calm reading rhythm while showing enough content to verify internal scrolling, responsive width, and the fixed overlay boundary.
              </p>
            </div>
            <template #footer>
              <BaseButton variant="secondary" @click="longModalOpen = false">Close review</BaseButton>
            </template>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Footer Slot</strong>
          <BaseButton size="compact" @click="footerModalOpen = true">Open footer</BaseButton>
          <BaseModal
            v-model:open="footerModalOpen"
            title="Footer actions"
            data-testid="modal-footer"
            @close="recordModalClose"
          >
            <p>The footer uses the caller-provided slot without submit semantics.</p>
            <template #footer>
              <BaseButton variant="ghost" @click="footerModalOpen = false">Later</BaseButton>
              <BaseButton variant="secondary" @click="footerModalOpen = false">Done</BaseButton>
            </template>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>No Footer</strong>
          <BaseButton size="compact" @click="noFooterModalOpen = true">Open without footer</BaseButton>
          <BaseModal
            v-model:open="noFooterModalOpen"
            title="Informational message"
            data-testid="modal-no-footer"
            @close="recordModalClose"
          >
            <p>No empty footer container is rendered.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Title + Description</strong>
          <BaseButton size="compact" @click="describedModalOpen = true">Open described modal</BaseButton>
          <BaseModal
            v-model:open="describedModalOpen"
            title="Accessible review"
            description="The dialog name and description use separate stable generated IDs."
            data-testid="modal-title-description"
            @close="recordModalClose"
          >
            <p>Inspect aria-labelledby and aria-describedby on the dialog.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>ariaLabel Fallback</strong>
          <BaseButton size="compact" @click="ariaLabelModalOpen = true">Open label fallback</BaseButton>
          <BaseModal
            v-model:open="ariaLabelModalOpen"
            aria-label="ARIA label fallback dialog"
            data-testid="modal-aria-label"
            @close="recordModalClose"
          >
            <p>This dialog intentionally omits a visible title.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Default Backdrop</strong>
          <BaseButton size="compact" @click="defaultBackdropModalOpen = true">Backdrop stays open</BaseButton>
          <BaseModal
            v-model:open="defaultBackdropModalOpen"
            title="Default backdrop policy"
            data-testid="modal-backdrop-default"
            @close="recordModalClose"
          >
            <p>Pointer input on the backdrop does not close this modal.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Opt-in Backdrop</strong>
          <BaseButton size="compact" @click="backdropCloseModalOpen = true">Backdrop closes</BaseButton>
          <BaseModal
            v-model:open="backdropCloseModalOpen"
            title="Opt-in backdrop close"
            close-on-backdrop
            data-testid="modal-backdrop-close"
            @close="recordModalClose"
          >
            <p>Only a direct pointer event on the backdrop closes this modal.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Escape Disabled</strong>
          <BaseButton size="compact" @click="escapeDisabledModalOpen = true">Open Escape disabled</BaseButton>
          <BaseModal
            v-model:open="escapeDisabledModalOpen"
            title="Escape is disabled"
            :close-on-escape="false"
            data-testid="modal-escape-disabled"
            @close="recordModalClose"
          >
            <p>Use the close button; Escape leaves the controlled state unchanged.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Initial Autofocus</strong>
          <BaseButton size="compact" @click="autofocusModalOpen = true">Open autofocus</BaseButton>
          <BaseModal
            v-model:open="autofocusModalOpen"
            title="Autofocus priority"
            data-testid="modal-autofocus"
            @close="recordModalClose"
          >
            <BaseInput autofocus aria-label="Preferred initial focus" placeholder="Autofocus target" />
            <BaseButton variant="secondary">Later focus target</BaseButton>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>No Focusable Content</strong>
          <BaseButton size="compact" @click="noFocusableModalOpen = true">Open panel fallback</BaseButton>
          <BaseModal
            v-model:open="noFocusableModalOpen"
            aria-label="No focusable content dialog"
            data-testid="modal-no-focusable"
            @close="recordModalClose"
          >
            <p>The dialog panel receives focus because the body has no focusable descendants.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Two Nested</strong>
          <BaseButton size="compact" @click="nestedParentOpen = true">Open parent</BaseButton>
          <BaseModal
            v-model:open="nestedParentOpen"
            title="Parent modal"
            data-testid="modal-nested-parent"
            @close="recordModalClose"
          >
            <p>The parent remains mounted and becomes inert while its child is topmost.</p>
            <BaseButton data-testid="modal-nested-child-trigger" @click="nestedChildOpen = true">Open child</BaseButton>
            <BaseModal
              v-model:open="nestedChildOpen"
              title="Nested child modal"
              data-testid="modal-nested-child"
              @close="recordModalClose"
            >
              <p>Escape closes this child first and restores focus to the parent opener.</p>
            </BaseModal>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Dropdown Inside</strong>
          <BaseButton size="compact" @click="dropdownInsideModalOpen = true">Open modal menu</BaseButton>
          <BaseModal
            v-model:open="dropdownInsideModalOpen"
            title="Dropdown inside modal"
            data-testid="modal-dropdown-inside"
            @close="recordModalClose"
          >
            <BaseDropdown v-model:open="modalInnerDropdownOpen" aria-label="Modal action menu">
              <template #trigger>
                <BaseButton variant="secondary">Open inner menu</BaseButton>
              </template>
              <BaseDropdownItem value="inspect">Inspect</BaseDropdownItem>
              <BaseDropdownItem value="archive">Archive</BaseDropdownItem>
            </BaseDropdown>
            <p>First Escape closes the menu; second Escape closes the modal.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Dropdown Then Modal</strong>
          <BaseDropdown
            v-model:open="dropdownBeforeModalMenuOpen"
            :close-on-outside="false"
            placement="top-start"
            aria-label="Pre-modal menu"
          >
            <template #trigger>
              <BaseButton variant="secondary" size="compact">Open menu first</BaseButton>
            </template>
            <BaseDropdownItem value="one">Menu remains below modal</BaseDropdownItem>
          </BaseDropdown>
          <BaseButton size="compact" @click="dropdownBeforeModalOpen = true">Then open modal</BaseButton>
          <BaseModal
            v-model:open="dropdownBeforeModalOpen"
            title="Modal above existing dropdown"
            data-testid="modal-dropdown-before"
            @close="recordModalClose"
          >
            <p>Escape closes the top modal before returning to the older dropdown.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>External Controlled</strong>
          <span>open: {{ controlledModalOpen }}</span>
          <BaseButton size="compact" @click="controlledModalOpen = true">External open</BaseButton>
          <BaseModal
            :open="controlledModalOpen"
            title="Externally controlled modal"
            data-testid="modal-controlled"
            @update:open="controlledModalOpen = $event"
            @close="recordModalClose"
          >
            <BaseButton variant="secondary" @click="controlledModalOpen = false">External close without reason</BaseButton>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Unmount While Open</strong>
          <BaseButton size="compact" @click="openUnmountModal">Open unmount proof</BaseButton>
          <BaseModal
            v-if="showUnmountModal"
            v-model:open="unmountModalOpen"
            title="Unmount cleanup proof"
            data-testid="modal-unmount-open"
            @close="recordModalClose"
          >
            <p>Unmounting releases Portal ownership, stack entry, focus listeners, inert state, and scroll lock.</p>
            <BaseButton variant="secondary" @click="showUnmountModal = false">Unmount now</BaseButton>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Opener Removed</strong>
          <BaseButton
            v-if="!openerRemoved"
            size="compact"
            @click="openRemovedOpenerModal"
          >
            Open then remove opener
          </BaseButton>
          <BaseButton variant="ghost" size="compact" data-testid="modal-opener-fallback">
            Safe fallback target
          </BaseButton>
          <BaseModal
            v-model:open="removedOpenerModalOpen"
            title="Removed opener fallback"
            data-testid="modal-opener-removed"
            @close="recordModalClose"
          >
            <p>Closing chooses a valid document focus target when the original opener no longer exists.</p>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Scroll Lock Proof</strong>
          <span>body overflow: {{ bodyOverflowValue }}</span>
          <BaseButton size="compact" @click="scrollLockModalOpen = true">Inspect lock</BaseButton>
          <BaseModal
            v-model:open="scrollLockModalOpen"
            title="Reference-counted scroll lock"
            data-testid="modal-scroll-lock"
            @close="recordModalClose"
          >
            <p>The body overflow value is restored exactly after the final modal owner releases.</p>
            <BaseButton variant="secondary" @click="nestedScrollModalOpen = true">Add nested lock owner</BaseButton>
            <BaseModal
              v-model:open="nestedScrollModalOpen"
              title="Second scroll owner"
              @close="recordModalClose"
            >
              <p>Closing this child leaves the parent scroll lock active.</p>
            </BaseModal>
          </BaseModal>
        </div>

        <div class="v2-lab__example">
          <strong>Background Blocking Proof</strong>
          <span>background attempts: {{ backgroundInteractionCount }}</span>
          <BaseButton
            variant="ghost"
            size="compact"
            data-testid="modal-background-target"
            @click="backgroundInteractionCount += 1"
          >
            Background target
          </BaseButton>
          <BaseButton size="compact" @click="backgroundBlockModalOpen = true">Block background</BaseButton>
          <BaseModal
            v-model:open="backgroundBlockModalOpen"
            title="Background interaction blocked"
            data-testid="modal-background-block"
            @close="recordModalClose"
          >
            <p>Application siblings are reversibly inert while the top modal is open.</p>
          </BaseModal>
        </div>
      </div>
    </section>

    <section class="v2-lab__section v2-lab__section--workbench" data-testid="workbench-components">
      <div class="v2-lab__section-heading">
        <h2>Workbench Composition</h2>
        <span>Operational hierarchy · normal / loading / empty / error / narrow</span>
      </div>

      <div class="v2-lab__workbench-canvas">
        <WorkbenchPageHeader
          eyebrow="TODAY · TEST OPERATIONS"
          title="质量工作台"
          description="聚合真实执行数据、失败关注项和测试资产状态，视觉层不持有业务状态。"
        >
          <template #actions>
            <BaseButton variant="secondary">查看执行记录</BaseButton>
            <BaseButton>新建测试</BaseButton>
          </template>
        </WorkbenchPageHeader>

        <WorkbenchMetricRail
          status-label="SYSTEM STATUS"
          status-title="运行稳定"
          status-detail="最近同步 2 分钟前"
          :items="workbenchMetrics"
        />

        <div class="v2-lab__workbench-grid">
          <WorkbenchPanel title="最近 7 次执行" subtitle="仅展示真实存在的时间范围">
            <template #actions>
              <WorkbenchStatus tone="success" label="通过率 91%" compact />
            </template>
            <WorkbenchTrendChart
              :labels="workbenchTrend.labels"
              :passed="workbenchTrend.passed"
              :failed="workbenchTrend.failed"
            />
          </WorkbenchPanel>

          <WorkbenchPanel title="需要关注" subtitle="按可证明的失败状态派生">
            <WorkbenchAttentionList
              :items="workbenchAttention"
              @action="workbenchActionCount += 1"
            />
          </WorkbenchPanel>
        </div>

        <div class="v2-lab__workbench-states">
          <WorkbenchPanel title="Loading">
            <div class="v2-lab__workbench-state-body">
              <BaseSkeleton variant="text" :lines="3" />
            </div>
          </WorkbenchPanel>
          <WorkbenchPanel title="Empty + 0 value">
            <WorkbenchMetricRail
              status-label="QUEUE"
              status-title="暂无排队任务"
              :items="workbenchZeroMetrics"
            />
            <WorkbenchTrendChart :labels="[]" :passed="[]" :failed="[]" />
          </WorkbenchPanel>
          <WorkbenchPanel title="Error + long text">
            <div class="v2-lab__workbench-state-body">
              <BaseErrorState
                title="无法加载跨服务回归执行记录"
                message="接口返回了可恢复错误；页面保留筛选条件，并提供键盘可达的重试操作。"
                action-label="重试"
                @action="retryCount += 1"
              />
            </div>
          </WorkbenchPanel>
        </div>

        <div class="v2-lab__workbench-narrow" aria-label="窄屏布局验证">
          <WorkbenchPageHeader
            title="窄屏工作区中的超长页面标题会自然换行"
            description="组合组件保持内容顺序和键盘焦点，不把信息压缩成不可读的图标。"
          >
            <template #actions>
              <BaseButton>键盘操作</BaseButton>
            </template>
          </WorkbenchPageHeader>
        </div>
      </div>
    </section>

    <output class="v2-lab__status" aria-live="polite" data-testid="lab-status">
      Button {{ buttonClicks }} · Icon {{ iconButtonClicks }} · Chip {{ chipSelectCount }} ·
      Card {{ cardActivations }} · Pagination {{ paginationEvents }} ·
      Empty {{ emptyActionCount }} · Retry {{ retryCount }}
      · Workbench {{ workbenchActionCount }}
    </output>
  </main>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  BaseBadge,
  BaseButton,
  BaseCard,
  BaseCheckbox,
  BaseChip,
  BaseDropdown,
  BaseDropdownItem,
  BaseEmptyState,
  BaseErrorState,
  BaseIconButton,
  BaseInput,
  BaseModal,
  BasePagination,
  BaseSelect,
  BaseSkeleton,
  BaseTable,
  BaseTextarea,
  BaseTooltip,
} from '../components/v2/base/index.js'
import {
  WorkbenchAttentionList,
  WorkbenchMetricRail,
  WorkbenchPageHeader,
  WorkbenchPanel,
  WorkbenchStatus,
  WorkbenchTrendChart,
} from '../components/v2/workbench/index.js'
import { getOverlayCount } from '../components/v2/overlay/overlayStack.js'
import { getV2PortalOwnerCount } from '../components/v2/overlay/portal.js'
import { getBodyScrollLockCount } from '../components/v2/overlay/scrollLock.js'

const LabIcon = defineComponent({
  name: 'LabIcon',
  setup() {
    return () => h(
      'svg',
      { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2' },
      [
        h('circle', { cx: '11', cy: '11', r: '7' }),
        h('path', { d: 'm16 16 4 4' }),
      ],
    )
  },
})

const buttonClicks = ref(0)
const iconButtonClicks = ref(0)
const iconPressed = ref(true)
const chipSelected = ref(false)
const chipSelectCount = ref(0)
const cardActivations = ref(0)
const normalInput = ref('')
const labeledInput = ref('已有内容')
const prefixInput = ref('')
const suffixInput = ref('contract')
const errorInput = ref('')
const selectOptions = [
  { value: 'development', label: 'Development' },
  { value: 'test', label: 'Test environment' },
  { value: 'production', label: 'Production', disabled: true },
]
const longSelectOptions = [
  { value: 'primary', label: 'Primary integration environment for cross-service release verification' },
  { value: 'fallback', label: 'Fallback environment' },
]
const selectDefault = ref('development')
const selectLabeled = ref('test')
const selectPlaceholder = ref('')
const selectSelected = ref('production')
const selectHover = ref('development')
const selectFocus = ref('test')
const selectRequired = ref('')
const selectError = ref('')
const selectLong = ref('primary')
const selectNarrow = ref('primary')
const textareaDefault = ref('')
const textareaLabeled = ref('{\n  "enabled": true\n}')
const textareaPlaceholder = ref('')
const textareaFocus = ref('Focus this field with Tab.')
const textareaError = ref('{ invalid json }')
const textareaMaxlength = ref('API case body')
const textareaLong = ref('This execution note intentionally contains a longer operational description so reviewers can inspect line wrapping, rhythm, readability, and vertical density without introducing an editor or auto-resize behavior.')
const textareaNarrow = ref('A narrow validation example with quiet metadata.')
const simpleTableColumns = [
  { key: 'name', label: 'NAME' },
  { key: 'owner', label: 'OWNER' },
  { key: 'updated', label: 'UPDATED' },
]
const simpleTableRows = [
  { id: 1, name: 'Authentication smoke suite', owner: 'Platform QA', updated: '4 min ago' },
  { id: 2, name: 'Checkout contract suite', owner: 'Commerce QA', updated: 'Yesterday' },
]
const resourceTableColumns = [
  { key: 'id', label: 'ID' },
  { key: 'case', label: 'CASE' },
  { key: 'method', label: 'METHOD' },
  { key: 'service', label: 'SERVICE / ENV' },
  { key: 'status', label: 'STATUS' },
  { key: 'updated', label: 'UPDATED' },
  { key: 'actions', label: 'ACTIONS' },
]
const resourceTableRows = [
  { id: 'API-1048', case: 'Administrator sign-in succeeds', path: '/api/auth/login', method: 'POST', service: 'Identity · Test', status: 'Passing', statusTone: 'success', updated: '4 min ago' },
  { id: 'API-1042', case: 'Search catalog by keyword and availability', path: '/api/products?keyword={keyword}', method: 'GET', service: 'Catalog · Test', status: 'Passing', statusTone: 'success', updated: '18 min ago' },
  { id: 'API-1039', case: 'Add available item to shopping cart', path: '/api/cart/items', method: 'POST', service: 'Cart · Pre-production', status: 'Failed', statusTone: 'danger', updated: '1 hr ago' },
  { id: 'API-1012', case: 'Remove member delivery address', path: '/api/members/{memberId}/addresses/{id}', method: 'DELETE', service: 'Member · Development', status: 'Draft', statusTone: 'neutral', updated: 'Jul 25' },
]
const longTableColumns = [
  { key: 'resource', label: 'RESOURCE' },
  { key: 'description', label: 'DESCRIPTION' },
  { key: 'ownership', label: 'OWNERSHIP' },
]
const longTableRows = [
  {
    id: 1,
    resource: 'Cross-service order fulfillment regression contract',
    description: 'Validates authentication, pricing, inventory reservation, fulfillment creation, and downstream reporting while preserving the complete diagnostic context for reviewers.',
    ownership: 'Commerce Quality Engineering',
  },
]
const checkboxValue = ref(false)
const indeterminateValue = ref(false)
const describedCheckbox = ref(false)
const labelOnlyCheckbox = ref(false)
const paginationPage = ref(50)
const paginationEvents = ref(0)
const emptyActionCount = ref(0)
const retryCount = ref(0)
const workbenchActionCount = ref(0)
const workbenchMetrics = [
  { key: 'projects', label: '活跃项目', value: '12', trend: '3 个环境在线', progress: 76, tone: 'info' },
  { key: 'cases', label: '测试资产', value: '1,248', trend: '本周新增 38', progress: 64, tone: 'success' },
  { key: 'runs', label: '今日执行', value: '86', trend: '较昨日 +12', progress: 82, tone: 'info' },
  { key: 'failed', label: '失败待查', value: '7', trend: '其中 2 项高优先级', progress: 18, tone: 'danger' },
]
const workbenchZeroMetrics = [
  { key: 'waiting', label: '等待中', value: '0', trend: '当前无任务', progress: 0, tone: 'neutral' },
]
const workbenchTrend = {
  labels: ['08-04', '08-05', '08-06', '08-07', '08-08', '08-09', '今天'],
  passed: [58, 64, 61, 73, 69, 82, 78],
  failed: [7, 4, 9, 5, 6, 3, 7],
}
const workbenchAttention = [
  { id: 'record-972', tone: 'danger', title: '结算接口回归失败', detail: '最近一次执行于 10:56，错误证据已保留', actionLabel: '查看记录' },
  { id: 'env-test', tone: 'warning', title: '测试环境响应偏慢', detail: '连续 3 次检查超过阈值', actionLabel: '检查环境' },
  { id: 'ui-empty', tone: 'info', title: 'UI 自动化尚无用例', detail: '创建首个浏览器用例后可启用视觉执行', actionLabel: '去创建' },
]
const showUnmountTooltip = ref(true)
const bottomStartOpen = ref(false)
const bottomEndOpen = ref(false)
const topStartOpen = ref(false)
const topEndOpen = ref(false)
const disabledTriggerOpen = ref(false)
const itemStatesOpen = ref(false)
const keepOpenOnSelect = ref(false)
const ignoreOutsideOpen = ref(false)
const matchWidthOpen = ref(false)
const noItemsOpen = ref(false)
const longTextOpen = ref(false)
const viewportEdgeOpen = ref(false)
const mutualAOpen = ref(false)
const mutualBOpen = ref(false)
const showUnmountDropdown = ref(true)
const unmountDropdownOpen = ref(false)
const controlledOpen = ref(false)
const dropdownSelectCount = ref(0)
const dropdownLastValue = ref('none')
const defaultModalOpen = ref(false)
const longModalOpen = ref(false)
const footerModalOpen = ref(false)
const noFooterModalOpen = ref(false)
const describedModalOpen = ref(false)
const ariaLabelModalOpen = ref(false)
const defaultBackdropModalOpen = ref(false)
const backdropCloseModalOpen = ref(false)
const escapeDisabledModalOpen = ref(false)
const autofocusModalOpen = ref(false)
const noFocusableModalOpen = ref(false)
const nestedParentOpen = ref(false)
const nestedChildOpen = ref(false)
const dropdownInsideModalOpen = ref(false)
const modalInnerDropdownOpen = ref(false)
const dropdownBeforeModalMenuOpen = ref(false)
const dropdownBeforeModalOpen = ref(false)
const controlledModalOpen = ref(false)
const showUnmountModal = ref(true)
const unmountModalOpen = ref(false)
const openerRemoved = ref(false)
const removedOpenerModalOpen = ref(false)
const scrollLockModalOpen = ref(false)
const nestedScrollModalOpen = ref(false)
const backgroundBlockModalOpen = ref(false)
const backgroundInteractionCount = ref(0)
const modalLastCloseReason = ref('none')
const activeFocusElement = ref('BODY')
const bodyOverflowValue = computed(() => {
  activeFocusElement.value
  return typeof document === 'undefined' ? 'unavailable' : document.body.style.overflow || 'initial'
})

function toggleIconPressed() {
  iconButtonClicks.value += 1
  iconPressed.value = !iconPressed.value
}

function toggleChip() {
  chipSelectCount.value += 1
  chipSelected.value = !chipSelected.value
}

function handlePaginationChange(nextPage) {
  paginationEvents.value += 1
  paginationPage.value = nextPage
}

function handleDropdownSelect(value) {
  dropdownSelectCount.value += 1
  dropdownLastValue.value = String(value)
}

function recordModalClose(reason) {
  modalLastCloseReason.value = reason
}

function openUnmountModal() {
  showUnmountModal.value = true
  nextTick(() => {
    unmountModalOpen.value = true
  })
}

function openRemovedOpenerModal() {
  removedOpenerModalOpen.value = true
  nextTick(() => {
    openerRemoved.value = true
  })
}

function updateActiveFocus(event) {
  const target = event?.target ?? document.activeElement
  activeFocusElement.value = target?.getAttribute?.('data-testid')
    || target?.getAttribute?.('aria-label')
    || target?.id
    || target?.tagName
    || 'none'
}

onMounted(() => {
  document.addEventListener('focusin', updateActiveFocus)
  updateActiveFocus()
})

onBeforeUnmount(() => {
  document.removeEventListener('focusin', updateActiveFocus)
})
</script>

<style scoped>
@layer v2-utilities {
  .v2-lab {
    min-height: 100vh;
    padding: var(--v2-space-5);
    color: var(--v2-text-primary);
    background: var(--v2-surface-canvas);
  }

  .v2-lab__header {
    max-width: var(--v2-layout-workspace-max);
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--v2-space-4);
    margin: 0 auto var(--v2-space-5);
  }

  .v2-lab__eyebrow,
  .v2-lab__intro,
  .v2-lab__section-heading span,
  .v2-lab__status {
    color: var(--v2-text-muted);
  }

  .v2-lab__section--workbench {
    background: var(--v2-surface-workspace);
    border-color: var(--v2-border-panel);
  }

  .v2-lab__workbench-canvas {
    display: grid;
    gap: var(--v2-space-3);
  }

  .v2-lab__workbench-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.65fr) minmax(280px, 0.85fr);
    gap: var(--v2-space-3);
  }

  .v2-lab__workbench-states {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: start;
    gap: var(--v2-space-3);
  }

  .v2-lab__workbench-state-body {
    padding: var(--v2-space-3);
  }

  .v2-lab__workbench-narrow {
    width: calc(var(--v2-space-7) * 6);
    max-width: 100%;
    padding: var(--v2-space-3);
    border: var(--v2-border-width) dashed var(--v2-border-panel);
    border-radius: var(--v2-radius-panel);
    background: var(--v2-surface-default);
  }

  @media (max-width: 1080px) {
    .v2-lab__workbench-grid,
    .v2-lab__workbench-states {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  .v2-lab__eyebrow {
    margin: 0 0 var(--v2-space-1);
    font-size: var(--v2-font-size-tiny);
    font-weight: var(--v2-font-weight-bold);
    letter-spacing: var(--v2-letter-spacing-wide);
    text-transform: uppercase;
  }

  .v2-lab__title {
    margin: 0;
    font-size: var(--v2-font-size-display);
    line-height: var(--v2-line-height-tight);
  }

  .v2-lab__intro {
    margin: var(--v2-space-2) 0 0;
  }

  .v2-lab__section {
    max-width: var(--v2-layout-workspace-max);
    padding: var(--v2-space-4);
    margin: 0 auto var(--v2-space-3);
    background: var(--v2-surface-default);
    border: var(--v2-border-width) solid var(--v2-border-default);
    border-radius: var(--v2-radius-md);
  }

  .v2-lab__section-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--v2-space-3);
    margin-bottom: var(--v2-space-3);
  }

  .v2-lab__section-heading h2 {
    margin: 0;
    font-size: var(--v2-font-size-section);
  }

  .v2-lab__section-heading span,
  .v2-lab__status {
    font-size: var(--v2-font-size-caption);
  }

  .v2-lab__row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--v2-space-2);
  }

  .v2-lab__grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(calc(var(--v2-space-7) * 4), 1fr));
    gap: var(--v2-space-3);
  }

  .v2-lab__control-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(calc(var(--v2-space-7) * 4), 1fr));
    gap: var(--v2-space-3);
    align-items: start;
  }

  .v2-lab__example small,
  .v2-lab__table-primary span,
  .v2-lab__table-loading span {
    color: var(--v2-text-muted);
    font-size: var(--v2-font-size-caption);
    line-height: var(--v2-line-height-caption);
  }

  .v2-lab__narrow {
    width: calc(var(--v2-space-7) * 3);
    max-width: 100%;
  }

  .v2-lab__stack {
    display: grid;
    gap: var(--v2-space-2);
  }

  .v2-lab__showcase-grid {
    display: grid;
    gap: var(--v2-space-3);
  }

  .v2-lab__table-stack,
  .v2-lab__table-loading,
  .v2-lab__table-primary {
    display: grid;
    gap: var(--v2-space-2);
    min-width: 0;
  }

  .v2-lab__table-state-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(calc(var(--v2-space-7) * 4), 1fr));
    gap: var(--v2-space-3);
  }

  .v2-lab__table-primary {
    gap: var(--v2-space-micro);
  }

  .v2-lab__table-primary strong,
  .v2-lab__table-primary span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .v2-lab__table-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--v2-space-1);
  }

  .v2-lab__overflow-frame {
    width: calc(var(--v2-space-7) * 7);
    max-width: 100%;
  }

  .v2-lab__example {
    display: grid;
    align-content: start;
    gap: var(--v2-space-2);
    min-width: 0;
    padding: var(--v2-space-2) var(--v2-space-3);
    background: var(--v2-surface-soft);
    border-radius: var(--v2-radius-sm);
  }

  .v2-lab__tooltip-row {
    padding: var(--v2-space-6) var(--v2-space-4);
  }

  .v2-lab__dropdown-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(calc(var(--v2-space-7) * 3), 1fr));
    gap: var(--v2-space-3);
  }

  .v2-lab__edge {
    justify-items: end;
  }

  .v2-lab__wide-trigger {
    width: calc(var(--v2-space-7) * 3);
  }

  .v2-lab__outside-target {
    width: 100%;
    min-height: var(--v2-control-height-compact);
    margin-top: var(--v2-space-3);
    color: var(--v2-text-muted);
    background: var(--v2-surface-soft);
    border: var(--v2-border-width) dashed var(--v2-border-default);
    border-radius: var(--v2-radius-sm);
  }

  .v2-lab__modal-proof {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(calc(var(--v2-space-7) * 2), 1fr));
    gap: var(--v2-space-2);
    margin: 0 0 var(--v2-space-3);
  }

  .v2-lab__modal-proof div {
    min-width: 0;
    padding: var(--v2-space-2);
    background: var(--v2-surface-soft);
    border-radius: var(--v2-radius-sm);
  }

  .v2-lab__modal-proof dt {
    color: var(--v2-text-muted);
    font-size: var(--v2-font-size-tiny);
    font-weight: var(--v2-font-weight-bold);
    letter-spacing: var(--v2-letter-spacing-wide);
    text-transform: uppercase;
  }

  .v2-lab__modal-proof dd {
    margin: var(--v2-space-micro) 0 0;
    overflow-wrap: anywhere;
    font-size: var(--v2-font-size-caption);
  }

  .v2-lab__modal-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(calc(var(--v2-space-7) * 3), 1fr));
    gap: var(--v2-space-3);
  }

  .v2-lab__modal-long-copy {
    display: grid;
    gap: var(--v2-space-2);
  }

  .v2-lab__modal-long-copy p,
  .v2-base-modal p {
    margin: 0;
    line-height: var(--v2-line-height-body);
  }

  .v2-lab__status {
    max-width: var(--v2-layout-workspace-max);
    display: block;
    margin: var(--v2-space-4) auto 0;
    text-align: center;
  }

  @media (max-width: 1240px) {
    .v2-lab {
      padding: var(--v2-space-4);
    }
  }

  @media (max-width: 480px) {
    .v2-lab {
      padding: var(--v2-space-2);
    }

    .v2-lab__section {
      padding: var(--v2-space-3);
    }

    .v2-lab__modal-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
}
</style>
